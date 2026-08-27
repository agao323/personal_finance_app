"""Ownership-adjusted net worth.

The single calculation every endpoint and chart calls. There is no other code path
that sums balances — see docs/ARCHITECTURE.md#ownership-is-applied-in-exactly-one-place.

The load-bearing subtlety is **"in force on ``as_of``"**: asking for net worth on a past
date must use that date's balances *and* that date's ownership stakes, never today's.
Get it wrong and every point on the history chart except the last is wrong, and it
looks entirely plausible.
"""

from __future__ import annotations

import calendar
import datetime as dt
from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, BalanceSnapshot, OwnershipStake
from app.models.enums import AccountKind
from app.services.balances import STALE_AFTER, BalanceAt, balance_in_force
from app.services.ownership import adjust, effective_stake, household_stake

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class AccountContribution:
    """One account's ownership-adjusted contribution, and where it came from."""

    account_id: int
    kind: AccountKind
    raw_balance: Decimal
    """Full balance, before the ownership stake. Positive for liabilities too."""
    adjusted_balance: Decimal
    """After the stake, rounded. Liabilities are still positive here."""
    percentage: Decimal
    balance_as_of: dt.date
    """The snapshot's date, which may predate ``as_of`` — see carry-forward."""
    is_stale: bool


@dataclass(frozen=True)
class NetWorth:
    as_of: dt.date
    viewer_id: int | None
    """``None`` means the household total across every stake."""

    net_worth: Decimal
    assets: Decimal
    liabilities: Decimal
    """Positive. ``net_worth`` is ``assets - liabilities``."""

    by_kind: dict[AccountKind, Decimal] = field(default_factory=dict)
    contributions: list[AccountContribution] = field(default_factory=list)
    stale_account_ids: list[int] = field(default_factory=list)

    @property
    def stale_count(self) -> int:
        return len(self.stale_account_ids)


def net_worth(session: Session, as_of: dt.date, viewer_id: int | None = None) -> NetWorth:
    """Ownership-adjusted net worth on ``as_of``.

    ``viewer_id`` selects whose share: a user id applies that user's stake, ``None``
    sums every stake on the account. A 50%-owned rental contributes half for the
    viewer and all of it for the household.

    Accounts are excluded — not counted as zero — when they had no snapshot by
    ``as_of``, when they closed on or before it, or when the viewer held no stake that
    day. Zero would be a claim about the balance; exclusion is the truth, which is
    that the account was not part of this net worth on that date.

    Stale balances are *included* and reported. Dropping them would make net worth
    silently fall the day a snapshot aged past the carry-forward cap, which is worse
    than showing a number with a warning attached.
    """
    contributions: list[AccountContribution] = []

    for account in session.execute(select(Account)).scalars():
        contribution = _contribution(session, account, as_of, viewer_id)
        if contribution is not None:
            contributions.append(contribution)

    # Totalled by the same helper the series uses, so the two paths cannot disagree
    # about how contributions roll up even if they disagree about nothing else.
    return _total(contributions, as_of, viewer_id)


def _contribution(
    session: Session, account: Account, as_of: dt.date, viewer_id: int | None
) -> AccountContribution | None:
    """One account's share, or ``None`` when it does not belong in this total."""
    # balance_in_force already excludes accounts closed on or before as_of and
    # accounts with no snapshot by then, and reports carry-forward staleness.
    balance = balance_in_force(session, account.id, as_of)
    if balance is None:
        return None

    if viewer_id is None:
        percentage = household_stake(session, account.id, as_of)
    else:
        stake = effective_stake(session, account.id, as_of, viewer_id)
        if stake is None:
            # The viewer held no stake that day. Not a zero balance — not their
            # account at all, on that date.
            return None
        percentage = stake

    if percentage == ZERO:
        return None

    return AccountContribution(
        account_id=account.id,
        kind=account.kind,
        raw_balance=balance.balance,
        # Rounded here, per account, by the one helper allowed to round. The total is
        # then the sum of these, so the figure on screen equals the sum of its rows.
        adjusted_balance=adjust(balance.balance, percentage),
        percentage=percentage,
        balance_as_of=balance.as_of,
        is_stale=balance.is_stale,
    )


def _walk(start: dt.date, end: dt.date, interval: str) -> list[dt.date]:
    """Dates from ``start`` to ``end`` inclusive at ``interval``.

    Month stepping walks calendar months rather than adding 30 days, so a monthly
    series lands on the same day each month instead of drifting backwards through the
    year.
    """
    dates: list[dt.date] = []
    cursor = start

    while cursor <= end:
        dates.append(cursor)
        if interval == "day":
            cursor += dt.timedelta(days=1)
        elif interval == "week":
            cursor += dt.timedelta(weeks=1)
        else:
            year, month = divmod(cursor.month, 12)
            year, month = cursor.year + year, month + 1
            # Clamp for short months: stepping from the 31st lands on the 28th/30th
            # rather than overflowing into the following month.
            day = min(cursor.day, calendar.monthrange(year, month)[1])
            cursor = dt.date(year, month, day)

    # The requested end is always a point, even when the interval overshoots it —
    # otherwise a chart's last value silently predates "today".
    if dates and dates[-1] != end:
        dates.append(end)
    return dates


def earliest_snapshot(session: Session) -> dt.date | None:
    """The first date any account has a balance, or ``None`` for an empty database."""
    return session.execute(select(func.min(BalanceSnapshot.as_of))).scalar_one_or_none()


@dataclass(frozen=True)
class _Ledger:
    """Every row a series needs, loaded once.

    The series used to call :func:`net_worth` per point, and each of those ran a query
    for the account list plus two per account. A 3-month daily chart was ~1,548 round
    trips to Neon; this is three, whatever the range.

    **This is a second reading of the same rules** — carry-forward, the staleness cap,
    closed accounts, half-open stake ranges — and that is the danger in it. The
    protection is `test_the_series_agrees_with_the_single_date_calculation`, which
    computes both ways over a fixture built to exercise each rule and asserts they
    match point for point. Change either path without the other and it fails.
    """

    accounts: list[Account]
    #: Per account, ascending by date. Searched for the latest at or before a date.
    snapshots: dict[int, list[BalanceSnapshot]]
    #: Per account, every stake row. Filtered by the half-open range per date.
    stakes: dict[int, list[OwnershipStake]]


def _load(session: Session) -> _Ledger:
    """Three queries, regardless of how many points the caller wants."""
    accounts = list(session.execute(select(Account).order_by(Account.id)).scalars())

    snapshots: dict[int, list[BalanceSnapshot]] = {}
    for snapshot in session.execute(
        select(BalanceSnapshot).order_by(BalanceSnapshot.account_id, BalanceSnapshot.as_of)
    ).scalars():
        snapshots.setdefault(snapshot.account_id, []).append(snapshot)

    stakes: dict[int, list[OwnershipStake]] = {}
    for stake in session.execute(select(OwnershipStake)).scalars():
        stakes.setdefault(stake.account_id, []).append(stake)

    return _Ledger(accounts=accounts, snapshots=snapshots, stakes=stakes)


def _ledger_balance(ledger: _Ledger, account: Account, as_of: dt.date) -> BalanceAt | None:
    """Mirrors :func:`balances.balance_in_force`, reading from memory.

    Closed accounts leave net worth on the day they close, and an account with no
    snapshot by ``as_of`` is excluded rather than counted as zero.
    """
    if account.closed_at is not None and account.closed_at <= as_of:
        return None

    rows = ledger.snapshots.get(account.id)
    if not rows:
        return None

    # The rows are sorted ascending, so the latest at or before `as_of` is the one
    # before the insertion point. `bisect_right` on the key puts a snapshot dated
    # exactly `as_of` on the left of the split, which is what "at or before" means.
    index = bisect_right(rows, as_of, key=lambda row: row.as_of)
    if index == 0:
        return None
    snapshot = rows[index - 1]

    return BalanceAt(
        balance=snapshot.balance,
        as_of=snapshot.as_of,
        source=snapshot.source,
        is_stale=(as_of - snapshot.as_of) > STALE_AFTER,
    )


def _ledger_percentage(
    ledger: _Ledger, account_id: int, as_of: dt.date, viewer_id: int | None
) -> Decimal | None:
    """Mirrors `ownership.effective_stake` / `household_stake`, reading from memory.

    Ranges are half-open — ``[effective_from, effective_to)`` — so the day a stake
    changes belongs to the new row, exactly as `ownership._in_force_on` decides it in
    SQL. `None` for the viewer means they held no stake that day, which excludes the
    account rather than zeroing it.
    """
    rows = ledger.stakes.get(account_id, ())
    in_force = [
        row
        for row in rows
        if row.effective_from <= as_of and (row.effective_to is None or row.effective_to > as_of)
    ]

    if viewer_id is None:
        total = ZERO
        for row in in_force:
            total += row.percentage
        return total

    for row in in_force:
        if row.owner_user_id == viewer_id:
            return row.percentage
    return None


def _ledger_contribution(
    ledger: _Ledger, account: Account, as_of: dt.date, viewer_id: int | None
) -> AccountContribution | None:
    """One account's share on a date. The in-memory twin of :func:`_contribution`."""
    balance = _ledger_balance(ledger, account, as_of)
    if balance is None:
        return None

    percentage = _ledger_percentage(ledger, account.id, as_of, viewer_id)
    if percentage is None or percentage == ZERO:
        return None

    return AccountContribution(
        account_id=account.id,
        kind=account.kind,
        raw_balance=balance.balance,
        # Still `adjust`, still per account, still the only rounding site.
        adjusted_balance=adjust(balance.balance, percentage),
        percentage=percentage,
        balance_as_of=balance.as_of,
        is_stale=balance.is_stale,
    )


def _total(
    contributions: list[AccountContribution], as_of: dt.date, viewer_id: int | None
) -> NetWorth:
    """Roll contributions into a NetWorth. Shared so both paths total identically."""
    assets = ZERO
    liabilities = ZERO
    by_kind: dict[AccountKind, Decimal] = {}

    for item in contributions:
        by_kind[item.kind] = by_kind.get(item.kind, ZERO) + item.adjusted_balance
        if item.kind is AccountKind.LIABILITY:
            liabilities += item.adjusted_balance
        else:
            assets += item.adjusted_balance

    return NetWorth(
        as_of=as_of,
        viewer_id=viewer_id,
        net_worth=assets - liabilities,
        assets=assets,
        liabilities=liabilities,
        by_kind=by_kind,
        contributions=contributions,
        stale_account_ids=[c.account_id for c in contributions if c.is_stale],
    )


def net_worth_series(
    session: Session,
    start: dt.date,
    end: dt.date,
    interval: str = "month",
    viewer_id: int | None = None,
) -> list[NetWorth]:
    """Net worth at each point between ``start`` and ``end``.

    Each point is computed independently with that date's balances and that date's
    stakes — never today's applied backwards. That is the whole reason the series
    cannot be a running total.

    The series is clipped to begin at the first snapshot in the database. Points
    before any balance exists are omitted rather than reported as zero: a chart
    starting at zero would show a fortune appearing overnight on the day the first
    account was added.

    **Three queries, whatever the range.** Everything is loaded once and the dates are
    walked in memory; see :class:`_Ledger` for why that is a risk and what pins it to
    :func:`net_worth`.
    """
    first = earliest_snapshot(session)
    if first is None:
        return []

    effective_start = max(start, first)
    if effective_start > end:
        return []

    ledger = _load(session)
    series: list[NetWorth] = []
    for day in _walk(effective_start, end, interval):
        contributions = [
            contribution
            for account in ledger.accounts
            if (contribution := _ledger_contribution(ledger, account, day, viewer_id)) is not None
        ]
        series.append(_total(contributions, day, viewer_id))
    return series
