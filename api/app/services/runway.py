"""Burn rate and months of runway.

**Burn is gross spend, excluding transfers. Income is not netted.** This tile answers
"how long if income stopped", which is the only version worth showing while income is
still arriving — see docs/PRODUCT.md#burn-and-runway.

Two rules keep the number from being quietly wrong in the dangerous direction, which
is *low*. A runway that reads too long is worse than no runway at all.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import AccountKind
from app.services.balances import balance_in_force
from app.services.ownership import adjust, effective_stake, household_stake
from app.services.spend import spend_by_category

ZERO = Decimal("0.00")

#: Trailing windows reported, in months.
WINDOWS = (3, 6, 12)

#: A month's spend is an outlier above this multiple of the window's median.
#:
#: Configurable because the right value depends on how lumpy the spending is. The
#: default is deliberately loose: it exists to stop a house deposit or a car purchase
#: from tripling the apparent burn rate, not to smooth ordinary variation. Excluding
#: too much is the dangerous direction — it makes runway look longer than it is.
DEFAULT_OUTLIER_MULTIPLE = Decimal("3")


@dataclass(frozen=True)
class BurnWindow:
    months: int
    average_monthly_spend: Decimal
    months_of_runway: float | None
    """``None`` when average spend is zero — dividing would be infinity, not a number."""
    months_counted: int
    months_excluded_as_outliers: int


@dataclass(frozen=True)
class Runway:
    liquid_assets: Decimal
    windows: list[BurnWindow]
    partial_month_excluded: bool


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def _complete_months_before(today: dt.date, count: int) -> list[tuple[dt.date, dt.date]]:
    """The ``count`` whole months ending with the one before ``today``'s.

    The current month is never included. It is partial by definition, and averaging a
    part-month in makes burn look artificially low *every single month* — always in
    the direction that overstates how long the money lasts.
    """
    months: list[tuple[dt.date, dt.date]] = []
    year, month = today.year, today.month

    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        months.append(_month_bounds(year, month))

    return list(reversed(months))


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def liquid_assets(session: Session, as_of: dt.date, viewer_id: int | None = None) -> Decimal:
    """Ownership-adjusted total of `kind='liquid_asset'` accounts only.

    Runway is about money you can actually spend. A house is not runway, and neither
    is a 401k you would pay a penalty to reach.
    """
    total = ZERO

    for account in session.execute(
        select(Account).where(Account.kind == AccountKind.LIQUID_ASSET)
    ).scalars():
        balance = balance_in_force(session, account.id, as_of)
        if balance is None:
            continue

        if viewer_id is None:
            percentage = household_stake(session, account.id, as_of)
        else:
            stake = effective_stake(session, account.id, as_of, viewer_id)
            if stake is None:
                continue
            percentage = stake

        total += adjust(balance.balance, percentage)

    return total


def _has_any_transaction(session: Session, start: dt.date, end: dt.date) -> bool:
    """Whether the month has data at all.

    A month with no transactions is missing data, not a month you spent nothing.
    Counting it as zero burn would drag the average down and inflate runway — the
    dangerous direction.
    """
    from app.models.transaction import Transaction

    return (
        session.execute(
            select(Transaction).where(Transaction.posted_at >= start, Transaction.posted_at <= end)
        ).first()
        is not None
    )


def burn_window(
    session: Session,
    months: int,
    today: dt.date,
    outlier_multiple: Decimal = DEFAULT_OUTLIER_MULTIPLE,
) -> tuple[Decimal, int, int]:
    """Average monthly spend over the trailing ``months`` complete months.

    Returns ``(average, months_counted, months_excluded)``. Months with no transaction
    data are skipped, and months spending more than ``outlier_multiple`` times the
    median are excluded so a single house deposit does not triple the apparent burn.
    """
    totals: list[Decimal] = []

    for start, end in _complete_months_before(today, months):
        if not _has_any_transaction(session, start, end):
            continue
        totals.append(spend_by_category(session, start, end).total)

    if not totals:
        return ZERO, 0, 0

    median = _median(totals)
    threshold = median * outlier_multiple

    # Only exclude when there is enough history for a median to mean anything. With
    # two months, one of them *is* the median and calling the other an outlier is
    # noise, not signal.
    kept = [value for value in totals if value <= threshold] if len(totals) >= 3 else totals
    if not kept:
        kept = totals

    average = (sum(kept, ZERO) / len(kept)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return average, len(kept), len(totals) - len(kept)


def runway(
    session: Session,
    today: dt.date | None = None,
    viewer_id: int | None = None,
    outlier_multiple: Decimal = DEFAULT_OUTLIER_MULTIPLE,
) -> Runway:
    """Months of runway from liquid assets at each trailing burn window."""
    today = today or dt.date.today()
    liquid = liquid_assets(session, today, viewer_id)

    windows: list[BurnWindow] = []
    for months in WINDOWS:
        average, counted, excluded = burn_window(session, months, today, outlier_multiple)
        windows.append(
            BurnWindow(
                months=months,
                average_monthly_spend=average,
                months_of_runway=(None if average <= ZERO else float(liquid / average)),
                months_counted=counted,
                months_excluded_as_outliers=excluded,
            )
        )

    return Runway(
        liquid_assets=liquid,
        windows=windows,
        # Always true: the current month is excluded unconditionally. Reported rather
        # than assumed so the UI can say so on the tile.
        partial_month_excluded=True,
    )
