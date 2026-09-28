"""Reading transactions: the filtered, paginated search behind the transactions screen.

Moved out of `routers/transactions.py` by ticket 082 so the screen and the advisor's
`transactions_search` tool run the same query. A second copy would agree with this one
until someone added a filter to either, and the chat would then find a charge the screen
could not — or miss one it shows.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.transaction import Transaction


@dataclass(frozen=True)
class TransactionFilters:
    """Every filter is optional; none set means every transaction."""

    date_from: dt.date | None = None
    date_to: dt.date | None = None
    account_id: int | None = None
    category_id: int | None = None
    #: `True`: only uncategorised rows. `False`: only categorised. `None`: both.
    uncategorised: bool | None = None
    #: Case-insensitive substring of the merchant **or** the description.
    search: str | None = None
    #: Bounds on the amount's size, ignoring its sign: "a charge of about $130" is a
    #: question about magnitude, and outflows are stored negative.
    magnitude_min: Decimal | None = None
    magnitude_max: Decimal | None = None


@dataclass(frozen=True)
class SearchResult:
    #: Newest first; each row with its account's name.
    rows: list[tuple[Transaction, str]]
    #: Matching rows in total, ignoring `limit` and `offset`.
    total: int


def _conditions(filters: TransactionFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.date_from is not None:
        conditions.append(Transaction.posted_at >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(Transaction.posted_at <= filters.date_to)
    if filters.account_id is not None:
        conditions.append(Transaction.account_id == filters.account_id)
    if filters.category_id is not None:
        conditions.append(Transaction.category_id == filters.category_id)
    if filters.uncategorised is True:
        conditions.append(Transaction.category_id.is_(None))
    elif filters.uncategorised is False:
        conditions.append(Transaction.category_id.isnot(None))
    if filters.magnitude_min is not None:
        conditions.append(func.abs(Transaction.amount) >= filters.magnitude_min)
    if filters.magnitude_max is not None:
        conditions.append(func.abs(Transaction.amount) <= filters.magnitude_max)
    if filters.search:
        pattern = f"%{filters.search}%"
        conditions.append(
            or_(Transaction.merchant.ilike(pattern), Transaction.description.ilike(pattern))
        )
    return conditions


def search(session: Session, filters: TransactionFilters, limit: int, offset: int) -> SearchResult:
    """Transactions matching `filters`, newest first, with a total for pagination."""
    conditions = _conditions(filters)

    total = session.execute(
        select(func.count()).select_from(Transaction).where(*conditions)
    ).scalar_one()

    rows = session.execute(
        select(Transaction, Account.name)
        .join(Account, Account.id == Transaction.account_id)
        .options(selectinload(Transaction.category))
        .where(*conditions)
        .order_by(Transaction.posted_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return SearchResult(rows=[(t, name) for t, name in rows], total=total)
