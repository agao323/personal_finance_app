"""How each goal stands: computed on read, never stored (ticket 111).

**Each goal is measured in its own scope.** A household goal counts every stake; a personal
goal counts its owner's. The person asking does not change a goal's progress — the goal says
whose money it is about.

- **Spending limit** — the category's spending this month to date and last complete month,
  from `spend.spend_totals` (so the transfer, refund and income rules are the dashboard's).
  A parent category counts its children. *On track* means spending is at or under the limit's
  pro-rata share of the month so far: $400 a month allows $200 by the 15th of a 30-day month.
- **Emergency fund** — liquid assets in the goal's scope over the six-month average monthly
  spending, from the runway service, against the target months. On track at or above target.
- **Savings target** — the linked accounts' ownership-adjusted balances in the goal's scope,
  from the net worth service (which rounds once, per account). With a date: the monthly amount
  still needed, rounded once in `numbers.py`, and on track when the balance is at or above the
  straight-line share of the target from the goal's creation to its date. Without one, on track
  while anything remains to save is not a claim this can make, so it is on track by default.

Every division happens at full precision and rounds once, at the edge.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.enums import AccountKind, GoalKind
from app.models.goal import Goal
from app.services import net_worth as net_worth_service
from app.services import runway as runway_service
from app.services.analysis.numbers import ZERO, quantize_money, ratio_bps, tenths
from app.services.spend import spend_totals

#: The burn window emergency funds are measured against, as runway's findings use.
RUNWAY_WINDOW = 6


@dataclass(frozen=True)
class Progress:
    as_of: dt.date
    on_track: bool
    stale: bool
    month_to_date: Decimal | None = None
    last_month: Decimal | None = None
    runway_months_tenths: int | None = None
    saved: Decimal | None = None
    remaining: Decimal | None = None
    monthly_needed: Decimal | None = None
    progress_bps: int | None = None


def _month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def _last_complete_month(today: dt.date) -> tuple[dt.date, dt.date]:
    end = _month_start(today) - dt.timedelta(days=1)
    return end.replace(day=1), end


def category_spend(session: Session, category_id: int, start: dt.date, end: dt.date) -> Decimal:
    """Spending on a category in `[start, end]`, a parent counting its children."""
    return sum(
        (
            amount
            for (bucket_id, _name, parent_id), amount in spend_totals(session, start, end).items()
            if bucket_id == category_id or parent_id == category_id
        ),
        ZERO,
    )


def _spending_limit(session: Session, goal: Goal, today: dt.date) -> Progress:
    assert goal.category_id is not None and goal.target_amount is not None
    limit = goal.target_amount
    month_to_date = category_spend(session, goal.category_id, _month_start(today), today)
    last_start, last_end = _last_complete_month(today)
    last_month = category_spend(session, goal.category_id, last_start, last_end)
    days = calendar.monthrange(today.year, today.month)[1]
    # At or under the pro-rata share of the limit: spent * days <= limit * day-of-month.
    on_pace = month_to_date * days <= limit * today.day
    return Progress(
        as_of=today,
        on_track=on_pace,
        stale=False,
        month_to_date=month_to_date,
        last_month=last_month,
        progress_bps=ratio_bps(month_to_date, limit),
    )


def _emergency_fund(session: Session, goal: Goal, today: dt.date) -> Progress:
    assert goal.target_months is not None
    viewer = goal.owner_user_id
    result = runway_service.runway(session, today=today, viewer_id=viewer)
    window = next(w for w in result.windows if w.months == RUNWAY_WINDOW)
    worth = net_worth_service.net_worth(session, today, viewer)
    stale = any(c.is_stale and c.kind is AccountKind.LIQUID_ASSET for c in worth.contributions)
    if window.average_monthly_spend <= ZERO:
        # No spending to measure against: the fund covers any number of months.
        return Progress(as_of=today, on_track=True, stale=stale)
    months = result.liquid_assets / window.average_monthly_spend
    return Progress(
        as_of=today,
        on_track=months >= goal.target_months,
        stale=stale,
        runway_months_tenths=tenths(months),
        progress_bps=ratio_bps(months, goal.target_months),
    )


def _months_between(start: dt.date, end: dt.date) -> int:
    """Whole calendar months from `start`'s month to `end`'s, at least one."""
    return max(1, (end.year - start.year) * 12 + (end.month - start.month))


def _savings_target(session: Session, goal: Goal, today: dt.date) -> Progress:
    assert goal.target_amount is not None
    target = goal.target_amount
    linked = {link.account_id for link in goal.links}
    worth = net_worth_service.net_worth(session, today, goal.owner_user_id)
    counted = [c for c in worth.contributions if c.account_id in linked]
    saved = sum((c.adjusted_balance for c in counted), ZERO)
    stale = any(c.is_stale for c in counted)
    remaining = max(ZERO, target - saved)

    monthly_needed: Decimal | None = None
    on_track = True
    if goal.target_date is not None and remaining > ZERO:
        if goal.target_date <= today:
            monthly_needed, on_track = remaining, False
        else:
            monthly_needed = quantize_money(remaining / _months_between(today, goal.target_date))
            started = goal.created_at.date()
            total_days = (goal.target_date - started).days
            elapsed = (today - started).days
            # At or above the straight-line share: saved * total >= target * elapsed.
            on_track = total_days <= 0 or saved * total_days >= target * elapsed
    return Progress(
        as_of=today,
        on_track=on_track,
        stale=stale,
        saved=saved,
        remaining=remaining,
        monthly_needed=monthly_needed,
        progress_bps=ratio_bps(saved, target),
    )


def progress(session: Session, goal: Goal, today: dt.date) -> Progress:
    if goal.kind is GoalKind.SPENDING_LIMIT:
        return _spending_limit(session, goal, today)
    if goal.kind is GoalKind.EMERGENCY_FUND:
        return _emergency_fund(session, goal, today)
    return _savings_target(session, goal, today)
