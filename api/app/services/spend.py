"""Spend rollups by category.

Two rules make these numbers believable, and both are easy to get wrong quietly.

**Transfers are not spending.** Moving $2,000 from checking to brokerage is not an
expense; if it lands in a spend chart the whole dashboard loses credibility. The
mechanism is ``categories.kind`` — see docs/ARCHITECTURE.md#transfers. Income is
excluded for the same structural reason: it is not spend, and netting it in would
answer a different question than the one the chart asks.

**Spend is never fractionally attributed by ownership.** A $60 grocery charge on a
jointly-owned card is $60 of spend, not $30. Splitting it has no correct answer — the
groceries were bought once — and it is not what the number is for. This is the one
place in the app where ownership deliberately does *not* apply.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.enums import CategoryKind
from app.models.transaction import Category, Transaction

ZERO = Decimal("0.00")

#: The bucket uncategorised spend lands in. Surfaced rather than hidden: it is the
#: prompt to add a rule, and hiding it would make the total quietly incomplete.
UNCATEGORISED = "Uncategorised"


@dataclass(frozen=True)
class Bucket:
    category_id: int | None
    category_name: str
    spend: Decimal
    #: Always computed — the comparison window is derived, never supplied, so there is
    #: no "no prior period" case at this layer. The schema still types it optional
    #: because a future caller might ask for a bare period without one.
    prior_spend: Decimal

    @property
    def change(self) -> Decimal:
        return self.spend - self.prior_spend


@dataclass(frozen=True)
class SpendSummary:
    start: dt.date
    end: dt.date
    total: Decimal
    buckets: list[Bucket]
    excluded_transfer_count: int


def _spend_query(start: dt.date, end: dt.date) -> Select[tuple[Transaction, Category]]:
    """Expense transactions in a half-open date range.

    An outer join, not an inner one: a transaction with no category still counts
    toward spend and belongs in the uncategorised bucket. An inner join would drop it
    and understate the total, which is the failure mode that makes people stop
    trusting the number.
    """
    return (
        select(Transaction, Category)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.posted_at >= start,
            Transaction.posted_at <= end,
            # Uncategorised rows have no kind, so they survive this filter and land in
            # the uncategorised bucket rather than being silently dropped.
            (Category.kind.is_(None)) | (Category.kind == CategoryKind.EXPENSE),
        )
    )


def _totals(
    session: Session, start: dt.date, end: dt.date, by_parent: bool
) -> dict[tuple[int | None, str], Decimal]:
    """Spend per bucket. Amounts are stored signed; outflows are negative."""
    totals: dict[tuple[int | None, str], Decimal] = {}

    for transaction, category in session.execute(_spend_query(start, end)).all():
        # The outer join makes `category` optional at runtime even though the Select's
        # static type does not say so.
        # Outflows are negative on the wire and in storage; spend is their magnitude.
        # An inflow sitting on an expense category (a refund) reduces spend, which is
        # correct — you did not spend that money after all.
        amount = -transaction.amount

        if category is None:
            key: tuple[int | None, str] = (None, UNCATEGORISED)
        elif by_parent and category.parent is not None:
            key = (category.parent.id, category.parent.name)
        else:
            key = (category.id, category.name)

        totals[key] = totals.get(key, ZERO) + amount

    return totals


def _count_transfers(session: Session, start: dt.date, end: dt.date) -> int:
    """Reported so the exclusion is visible rather than merely true."""
    rows = session.execute(
        select(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.posted_at >= start,
            Transaction.posted_at <= end,
            Category.kind == CategoryKind.TRANSFER,
        )
    ).all()
    return len(rows)


def prior_period(start: dt.date, end: dt.date) -> tuple[dt.date, dt.date]:
    """The equal-length window immediately before ``start``.

    Length-based rather than calendar-based: comparing a 31-day January against a
    28-day February would show a spending drop that is really just a shorter month.
    """
    span = end - start
    prior_end = start - dt.timedelta(days=1)
    return prior_end - span, prior_end


def spend_by_category(
    session: Session, start: dt.date, end: dt.date, by_parent: bool = False
) -> SpendSummary:
    """Spend between ``start`` and ``end`` inclusive, with a prior-period comparison."""
    current = _totals(session, start, end, by_parent)
    prior_start, prior_end = prior_period(start, end)
    prior = _totals(session, prior_start, prior_end, by_parent)

    buckets = [
        Bucket(
            category_id=key[0],
            category_name=key[1],
            spend=amount,
            prior_spend=prior.get(key, ZERO),
        )
        # Largest first: the chart and the table both lead with where the money went.
        for key, amount in sorted(current.items(), key=lambda item: -item[1])
    ]

    return SpendSummary(
        start=start,
        end=end,
        total=sum((b.spend for b in buckets), ZERO),
        buckets=buckets,
        excluded_transfer_count=_count_transfers(session, start, end),
    )
