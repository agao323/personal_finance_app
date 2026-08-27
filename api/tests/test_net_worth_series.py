"""The series path, and the thing that keeps it honest.

`net_worth_series` no longer calls `net_worth` per point — it loads accounts, snapshots
and stakes once and walks the dates in memory, which took a 3-month daily chart from
~1,548 queries to 4. That means there are now **two readings of the same rules**:
carry-forward, the 90-day staleness cap, closed-account exclusion, and half-open stake
ranges.

`test_the_series_agrees_with_the_single_date_calculation` is what stops them drifting.
It is not a nice-to-have around the edges of this change; it is the change's safety net,
and it should fail if either path is edited without the other.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.services.balances import record_balance
from app.services.net_worth import _walk, net_worth, net_worth_series
from app.services.ownership import create_initial_stake, transition_stake


def _money(value: str) -> Decimal:
    return Decimal(value)


def _rich_history(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    """A history that exercises every rule the two paths could disagree about.

    Deliberately not a tidy fixture: a part-owned account, a stake that changes
    mid-history, an account that closes, one that starts late, and one whose balance
    goes stale. If the in-memory reading of any rule drifts, one of these breaks.
    """
    # Fully owned, updated regularly.
    checking = make_account(name="Checking", kind="liquid_asset", subtype="checking")
    create_initial_stake(db_session, checking, owner_id, dt.date(2026, 1, 1))
    for month, amount in ((1, "1000.00"), (3, "1500.00"), (6, "2000.00")):
        record_balance(db_session, checking, dt.date(2026, month, 1), _money(amount))

    # Part-owned by the household, and the split changes in April.
    rental = make_account(name="Rental", kind="illiquid_asset", subtype="real_estate")
    create_initial_stake(db_session, rental, owner_id, dt.date(2026, 1, 1), Decimal("60.00"))
    transition_stake(db_session, rental, owner_id, Decimal("40.00"), dt.date(2026, 4, 1))
    create_initial_stake(db_session, rental, partner_id, dt.date(2026, 4, 1), Decimal("20.00"))
    record_balance(db_session, rental, dt.date(2026, 1, 1), _money("300000.00"))
    record_balance(db_session, rental, dt.date(2026, 5, 1), _money("310000.00"))

    # A liability that is paid off and closes in May.
    loan = make_account(
        name="Car loan", kind="liability", subtype="auto_loan", closed_at=dt.date(2026, 5, 15)
    )
    create_initial_stake(db_session, loan, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, loan, dt.date(2026, 1, 1), _money("12000.00"))
    record_balance(db_session, loan, dt.date(2026, 4, 1), _money("9000.00"))

    # Opened late — excluded before its first snapshot, never zero.
    brokerage = make_account(name="Brokerage", kind="liquid_asset", subtype="brokerage")
    create_initial_stake(db_session, brokerage, owner_id, dt.date(2026, 4, 15))
    record_balance(db_session, brokerage, dt.date(2026, 4, 15), _money("5000.00"))

    # One snapshot in January and never again: stale from April onwards.
    forgotten = make_account(name="Old HSA", kind="liquid_asset", subtype="hsa")
    create_initial_stake(db_session, forgotten, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, forgotten, dt.date(2026, 1, 1), _money("800.00"))

    db_session.flush()


def test_the_series_agrees_with_the_single_date_calculation(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    """The safety net for loading once instead of querying per point.

    `net_worth` is deliberately untouched by that change and remains the reference: it
    is what `/net-worth`, the export and the dashboard's headline figure all use. This
    asserts the fast path produces exactly what calling the reference per date would,
    including the stale counts and the assets/liabilities split.
    """
    _rich_history(db_session, make_account, owner_id, partner_id)
    start, end = dt.date(2026, 1, 1), dt.date(2026, 8, 1)

    for viewer in (owner_id, partner_id, None):
        for interval in ("day", "week", "month"):
            series = net_worth_series(db_session, start, end, interval, viewer)
            expected = [net_worth(db_session, day, viewer) for day in _walk(start, end, interval)]

            # Tripwires. Comparing two empty lists passes and proves nothing, and a
            # fixture that silently produced no contributions would do exactly that —
            # this session has already shipped one vacuously-passing guard.
            assert series, (interval, viewer)
            assert any(point.contributions for point in series), (interval, viewer)
            assert len({point.net_worth for point in series}) > 1, (
                interval,
                viewer,
                "net worth never changes, so the fixture is not exercising anything",
            )

            assert len(series) == len(expected), (interval, viewer)
            for fast, reference in zip(series, expected, strict=True):
                context = (interval, viewer, fast.as_of)
                assert fast.as_of == reference.as_of, context
                assert fast.net_worth == reference.net_worth, context
                assert fast.assets == reference.assets, context
                assert fast.liabilities == reference.liabilities, context
                assert fast.by_kind == reference.by_kind, context
                assert fast.stale_account_ids == reference.stale_account_ids, context


def test_the_series_agrees_on_contributions_too(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    """Per-account rows, not just the totals.

    Two paths could agree on a total while disagreeing about which account contributed
    what — and since rounding happens per account, an off-by-one-cent split would show
    up here first.
    """
    _rich_history(db_session, make_account, owner_id, partner_id)
    start, end = dt.date(2026, 1, 1), dt.date(2026, 8, 1)

    series = net_worth_series(db_session, start, end, "week", owner_id)
    expected = [net_worth(db_session, day, owner_id) for day in _walk(start, end, "week")]

    for fast, reference in zip(series, expected, strict=True):
        assert [
            (c.account_id, c.raw_balance, c.adjusted_balance, c.percentage, c.is_stale)
            for c in fast.contributions
        ] == [
            (c.account_id, c.raw_balance, c.adjusted_balance, c.percentage, c.is_stale)
            for c in reference.contributions
        ], fast.as_of


def test_the_query_count_does_not_grow_with_the_range(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    """The regression guard.

    The old implementation ran one query for the account list plus two per account, per
    point — 1,548 for a 3-month daily chart against nine accounts, each one a network
    round trip in production. A future change that reintroduces a per-point query should
    fail here rather than just getting slower, because slower is invisible until someone
    complains about the chart.
    """
    _rich_history(db_session, make_account, owner_id, partner_id)
    counted = 0

    def _count(*_args: object, **_kwargs: object) -> None:
        nonlocal counted
        counted += 1

    connection = db_session.connection()
    event.listen(connection.engine, "before_cursor_execute", _count)
    try:
        long_series = net_worth_series(
            db_session, dt.date(2026, 1, 1), dt.date(2026, 8, 1), "day", owner_id
        )
    finally:
        event.remove(connection.engine, "before_cursor_execute", _count)

    assert len(long_series) > 200, "the range must be long enough for per-point cost to show"
    # earliest_snapshot, accounts, snapshots, stakes. Generous ceiling so an extra
    # bookkeeping query is not a failure, but 200+ points cannot each add one.
    assert counted <= 10, f"{counted} queries for {len(long_series)} points"
