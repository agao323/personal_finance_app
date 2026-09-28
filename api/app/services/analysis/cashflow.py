"""Cashflow: income, spend, net and savings rate, month by month.

Income has been classified since v1 so that it stays out of spend, and it has never been
shown. This is its first computation.

PRODUCT keeps **gross** burn on the runway tile — "how long if income stopped" — and this
does not change that. Net figures belong here, in the advisor and the Insights panel.

Like spend, cashflow is **not split by ownership**: a salary into a joint account is the
household's income, not half of it.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CategoryKind
from app.models.transaction import Category, Transaction
from app.services.analysis.numbers import ZERO, ratio_bps
from app.services.runway import has_any_transaction
from app.services.spend import spend_totals


@dataclass(frozen=True)
class MonthFlow:
    month: dt.date
    """The first day of the month."""
    income: Decimal
    spend: Decimal

    @property
    def net(self) -> Decimal:
        return self.income - self.spend

    @property
    def savings_rate_bps(self) -> int | None:
        """Net over income. `None` without income; negative when spending exceeded it."""
        return ratio_bps(self.net, self.income) if self.income > 0 else None


@dataclass(frozen=True)
class Cashflow:
    months: list[MonthFlow]
    #: Complete months in the window that had no transactions at all.
    skipped: list[dt.date]

    @property
    def income(self) -> Decimal:
        return sum((m.income for m in self.months), ZERO)

    @property
    def spend(self) -> Decimal:
        return sum((m.spend for m in self.months), ZERO)

    @property
    def net(self) -> Decimal:
        return self.income - self.spend

    @property
    def savings_rate_bps(self) -> int | None:
        return ratio_bps(self.net, self.income) if self.income > 0 else None


def income_between(session: Session, start: dt.date, end: dt.date) -> Decimal:
    """Income in `[start, end]`: rows in income-kind categories, signed as stored.

    Only categorised income counts. An uncategorised inflow is not assumed to be income —
    it could as easily be a refund or a transfer nobody marked.
    """
    amounts = session.execute(
        select(Transaction.amount)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.posted_at >= start,
            Transaction.posted_at <= end,
            Category.kind == CategoryKind.INCOME,
        )
    ).scalars()
    return sum(amounts, ZERO)


def monthly(session: Session, today: dt.date, months: int) -> Cashflow:
    """The `months` complete months before `today`'s, oldest first, skipping empty ones."""
    year, month = today.year, today.month
    starts: list[dt.date] = []
    for _ in range(months):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        starts.append(dt.date(year, month, 1))
    starts.reverse()

    flows: list[MonthFlow] = []
    skipped: list[dt.date] = []
    for start in starts:
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        if not has_any_transaction(session, start, end):
            skipped.append(start)
            continue
        spend = sum(spend_totals(session, start, end).values(), ZERO)
        flows.append(
            MonthFlow(month=start, income=income_between(session, start, end), spend=spend)
        )
    return Cashflow(months=flows, skipped=skipped)
