"""The asset mix: `ownership.split`, each account by class in both scopes, unknown kept apart,
drift from the target mix, cash drag, the two findings and `allocation_get`."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.account import Account, OwnershipStake
from app.models.enums import AssetClass, GoalKind
from app.models.goal import Goal
from app.schemas.advisor import FindingKind
from app.schemas.common import ViewScope
from app.services import allocations
from app.services import findings as findings_service
from app.services.analysis import allocation
from app.services.balances import record_balance
from app.services.ownership import create_initial_stake, split

JAN = dt.date(2026, 1, 1)
MARCH_3 = dt.date(2026, 3, 3)
TODAY = dt.date(2026, 8, 18)
CENT = Decimal("0.01")


# ── split ─────────────────────────────────────────────────────────────────────


@given(
    cents=st.integers(min_value=-(10**12), max_value=10**12),
    weights=st.lists(
        st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=6,
    ).filter(lambda w: sum(w) > 0),
)
def test_split_sums_to_the_whole_and_each_part_is_within_a_cent(
    cents: int, weights: list[Decimal]
) -> None:
    amount = Decimal(cents).scaleb(-2)

    parts = split(amount, weights)

    assert sum(parts, Decimal(0)) == amount
    total = sum(weights, Decimal(0))
    for part, weight in zip(parts, weights, strict=True):
        assert part == part.quantize(CENT)
        assert abs(part - amount * weight / total) < CENT


def test_split_gives_leftover_cents_to_the_largest_remainders() -> None:
    assert split(Decimal("100.00"), [Decimal(1)] * 3) == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert split(Decimal("500.01"), [Decimal(60), Decimal(40)]) == [
        Decimal("300.01"),  # 300.006: the larger remainder
        Decimal("200.00"),
    ]
    assert split(Decimal("10.00"), [Decimal(0), Decimal(100)]) == [
        Decimal("0.00"),
        Decimal("10.00"),
    ]


@pytest.mark.parametrize(
    ("amount", "weights"),
    [
        (Decimal("1.005"), [Decimal(1)]),  # not already rounded
        (Decimal("1.00"), []),
        (Decimal("1.00"), [Decimal(0)]),
        (Decimal("1.00"), [Decimal(-1), Decimal(2)]),
    ],
)
def test_split_refuses_what_it_cannot_divide(amount: Decimal, weights: list[Decimal]) -> None:
    with pytest.raises(ValueError):
        split(amount, weights)


# ── the mix ───────────────────────────────────────────────────────────────────


@pytest.fixture
def own(db_session: Session, make_account: Callable[..., int], owner_id: int) -> Callable[..., int]:
    """An asset account the owner holds `stake`% of, with a balance today."""

    def _own(
        name: str, subtype: str, balance: str, kind: str = "liquid_asset", stake: str = "100"
    ) -> int:
        account = make_account(name=name, kind=kind, subtype=subtype)
        create_initial_stake(db_session, account, owner_id, JAN, Decimal(stake))
        record_balance(db_session, account, TODAY, Decimal(balance))
        return account

    return _own


def _set(db_session: Session, account_id: int, on: dt.date = MARCH_3, **pcts: str) -> None:
    allocations.set_allocation(
        db_session,
        db_session.get_one(Account, account_id),
        {AssetClass(cls): Decimal(pct) for cls, pct in pcts.items()},
        on,
    )


def _row(mix: allocation.Mix, account_id: int) -> allocation.AccountMix:
    return next(a for a in mix.accounts if a.account_id == account_id)


def test_the_50_percent_rental_in_both_scopes(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    # Half belongs to a co-investor outside the household, so both scopes see half.
    rental = own("Rental", "real_estate", "300000.01", kind="illiquid_asset", stake="50")

    for viewer in (owner_id, None):
        row = _row(allocation.mix(db_session, TODAY, viewer, owner_id), rental)
        assert (row.status, row.value) == ("derived", Decimal("150000.01"))  # .005, half-up
        assert row.parts == {AssetClass.REAL_ESTATE: Decimal("150000.01")}
        assert row.investable is False


def test_a_shared_account_splits_its_adjusted_balance_in_each_scope(
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    shared = make_account(name="Joint brokerage", subtype="brokerage")
    for user in (owner_id, partner_id):
        db_session.add(
            OwnershipStake(
                account_id=shared, owner_user_id=user, percentage=Decimal("50"), effective_from=JAN
            )
        )
    record_balance(db_session, shared, TODAY, Decimal("1000.01"))
    _set(db_session, shared, us_equity="60", bonds="40")

    mine = _row(allocation.mix(db_session, TODAY, owner_id, owner_id), shared)
    household = _row(allocation.mix(db_session, TODAY, None, owner_id), shared)

    assert mine.value == Decimal("500.01")
    assert mine.parts == {
        AssetClass.US_EQUITY: Decimal("300.01"),
        AssetClass.BONDS: Decimal("200.00"),
    }
    assert household.parts == {
        AssetClass.US_EQUITY: Decimal("600.01"),
        AssetClass.BONDS: Decimal("400.00"),
    }
    assert mine.entered_on == MARCH_3


def test_unknown_is_reported_as_unknown_never_folded_into_a_class(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    brokerage = own("Brokerage", "brokerage", "10000.00")
    own("Savings", "savings", "2000.00")

    mix = allocation.mix(db_session, TODAY, owner_id, owner_id)

    row = _row(mix, brokerage)
    assert (row.status, row.parts, row.entered_on) == ("unknown", {}, None)
    assert mix.unknown == Decimal("10000.00")
    assert mix.by_class[AssetClass.CASH] == Decimal("2000.00")
    assert sum(mix.by_class.values()) + mix.unknown == mix.total == Decimal("12000.00")
    # 10,000 of 12,000 investable-or-unknown is unknown: too much to state drift.
    assert mix.drift_withheld is True
    assert mix.drift == []


def test_class_totals_sum_exactly_to_every_asset(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    own("Checking", "checking", "1234.57", stake="50")  # 617.285 → 617.29
    b = own("Brokerage", "brokerage", "3333.33")
    four = own("401k", "401k", "10000.01", kind="illiquid_asset")
    _set(db_session, b, us_equity="33.33", intl_equity="33.33", bonds="33.34")
    _set(db_session, four, us_equity="70", intl_equity="20", bonds="10")

    mix = allocation.mix(db_session, TODAY, owner_id, owner_id)

    assert sum(mix.by_class.values()) == mix.total == Decimal("617.29") + Decimal("13333.34")
    for row in mix.accounts:
        assert sum(row.parts.values(), Decimal(0)) == row.value


# ── drift and cash drag ───────────────────────────────────────────────────────


def test_drift_is_measured_on_the_investable_base_against_the_default_target(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    b = own("Brokerage", "brokerage", "10000.00")
    own("Savings", "savings", "2000.00")
    own("House", "real_estate", "500000.00", kind="illiquid_asset")  # left out of drift
    _set(db_session, b, us_equity="100")

    mix = allocation.mix(db_session, TODAY, owner_id, owner_id)

    assert mix.investable == Decimal("12000.00")
    assert mix.target_defaults is True
    assert {d.asset_class: (d.actual_bps, d.target_bps) for d in mix.drift} == {
        AssetClass.US_EQUITY: (8333, 4000),
        AssetClass.INTL_EQUITY: (0, 2000),
        AssetClass.BONDS: (0, 3500),
        AssetClass.CASH: (1667, 500),
        AssetClass.OTHER: (0, 0),
    }


@pytest.fixture
def spending(
    make_transaction: Callable[..., int],
    make_account: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """$1,000 of groceries in each of the six complete months before TODAY."""
    card = make_account(name="Everyday card", kind="liability", subtype="credit_card")
    for month in range(2, 8):
        make_transaction(
            card, dt.date(2026, month, 10), "-1000.00", category_id=category_ids["Groceries"]
        )


@pytest.mark.usefixtures("spending")
def test_cash_beyond_six_months_of_spending_is_drag(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    own("Savings", "savings", "20000.00")
    own("Checking", "checking", "1000.00")

    drag = allocation.mix(db_session, TODAY, owner_id, owner_id).cash_drag

    assert drag is not None
    assert (drag.monthly_burn, drag.fund_months, drag.from_goal) == (
        Decimal("1000.00"),
        Decimal("6"),
        False,
    )
    assert (drag.fund_target, drag.beyond) == (Decimal("6000.00"), Decimal("15000.00"))


@pytest.mark.usefixtures("spending")
def test_an_emergency_fund_goal_sets_the_months(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    own("Savings", "savings", "20000.00")
    db_session.add(
        Goal(
            kind=GoalKind.EMERGENCY_FUND,
            name="A year of cash",
            target_months=Decimal("12"),
            created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
    )
    db_session.flush()

    drag = allocation.mix(db_session, TODAY, owner_id, owner_id).cash_drag

    assert drag is not None and drag.from_goal is True
    assert (drag.fund_target, drag.beyond) == (Decimal("12000.00"), Decimal("8000.00"))


def test_no_spending_history_means_no_cash_drag_figure(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    own("Savings", "savings", "20000.00")

    assert allocation.mix(db_session, TODAY, owner_id, owner_id).cash_drag is None


# ── findings ──────────────────────────────────────────────────────────────────


def _found(db_session: Session, owner_id: int, kind: FindingKind) -> list[str]:
    return [
        f.title
        for f in findings_service.findings(db_session, TODAY, ViewScope.MINE, owner_id)
        if f.kind is kind
    ]


def test_allocation_drift_names_the_class_furthest_from_target(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    b = own("Brokerage", "brokerage", "10000.00")
    own("Savings", "savings", "2000.00")
    _set(db_session, b, us_equity="100")

    assert _found(db_session, owner_id, FindingKind.ALLOCATION_DRIFT) == [
        "Your mix is 43.33 points over target on US stocks"
    ]


def test_no_drift_finding_within_five_points(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    b = own("Brokerage", "brokerage", "9500.00")
    own("Savings", "savings", "500.00")  # 5% cash, on target
    # 40/20/35 of the whole is 42.1/21.1/36.8 of the brokerage: every class within 5 points.
    _set(db_session, b, us_equity="42.1", intl_equity="21.1", bonds="36.8")

    assert _found(db_session, owner_id, FindingKind.ALLOCATION_DRIFT) == []


@pytest.mark.usefixtures("spending")
@pytest.mark.parametrize(
    ("savings", "titles"),
    [
        ("10999.99", []),  # 4,999.99 beyond a $6,000 fund
        ("11000.00", ["About $5,000.00 in cash beyond your emergency fund"]),
    ],
)
def test_cash_drag_from_5000_dollars_beyond_the_fund(
    db_session: Session, own: Callable[..., int], owner_id: int, savings: str, titles: list[str]
) -> None:
    own("Savings", "savings", savings)

    assert _found(db_session, owner_id, FindingKind.CASH_DRAG) == titles


# ── the tool ──────────────────────────────────────────────────────────────────


def test_allocation_get_states_when_each_allocation_was_entered(
    db_session: Session, own: Callable[..., int], owner_id: int
) -> None:
    b = own("Brokerage", "brokerage", "10000.00")
    own("Old IRA", "ira", "4000.00", kind="illiquid_asset")
    own("Savings", "savings", "2000.00")
    _set(db_session, b, us_equity="60", intl_equity="40")

    outcome = load_all().run(
        "allocation_get",
        {"view": None},
        ToolContext(
            today=TODAY,
            user_id=owner_id,
            view=ViewScope.MINE,
            sessions=savepoint_read_only(db_session),
        ),
    )

    assert outcome.status == "ok"
    content = outcome.content
    assert '"entered_on":"2026-03-03"' in content
    assert '"status":"unknown"' in content
    assert "$4,000.00 [c1.unknown]" in content
    assert "[c1.drift.0.drift_pct]" in content
