"""Transactions, and the manual category override.

This is the only place that writes ``category_source='manual'``. Ticket 022's rules
engine refuses to overwrite that value, so the two together are what make re-running
rules over all history safe: a pattern can reclassify anything it assigned itself, and
nothing a person decided.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.enums import CategorySource
from app.models.transaction import Category, Transaction
from app.schemas.common import ErrorResponse, Page, to_cents
from app.schemas.transaction import (
    BulkCategorise,
    BulkCategoriseResult,
    BulkTransfer,
    BulkTransferResult,
    CategoryRead,
    TransactionList,
    TransactionRead,
    TransactionUpdate,
)

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


def _to_read(transaction: Transaction, account_name: str) -> TransactionRead:
    return TransactionRead(
        id=transaction.id,
        account_id=transaction.account_id,
        account_name=account_name,
        posted_at=transaction.posted_at,
        amount_cents=to_cents(transaction.amount),
        merchant=transaction.merchant,
        description=transaction.description,
        category=(
            None
            if transaction.category is None
            else CategoryRead(
                id=transaction.category.id,
                name=transaction.category.name,
                parent_id=transaction.category.parent_id,
                kind=transaction.category.kind.value,
            )
        ),
        category_source=transaction.category_source,
        transfer_group_id=transaction.transfer_group_id,
    )


def _require_category(session: Session, category_id: int | None) -> None:
    """404 rather than a foreign-key error surfacing as a 500."""
    if category_id is None:
        return
    if session.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")


@router.get("", response_model=TransactionList)
def list_transactions(
    session: DbSession,
    user: CurrentUser,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    account_id: Annotated[int | None, Query()] = None,
    category_id: Annotated[int | None, Query()] = None,
    uncategorised: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionList:
    """Transactions, newest first, with filters and a total for pagination.

    `uncategorised=true` is the filter the dashboard links to: uncategorised spend is
    surfaced prominently as a prompt to add a rule, and this is where that prompt
    leads.
    """
    filters = []
    if date_from is not None:
        filters.append(Transaction.posted_at >= date_from)
    if date_to is not None:
        filters.append(Transaction.posted_at <= date_to)
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if uncategorised is True:
        filters.append(Transaction.category_id.is_(None))
    elif uncategorised is False:
        filters.append(Transaction.category_id.isnot(None))
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(Transaction.merchant.ilike(pattern), Transaction.description.ilike(pattern))
        )

    total = session.execute(
        select(func.count()).select_from(Transaction).where(*filters)
    ).scalar_one()

    rows = session.execute(
        select(Transaction, Account.name)
        .join(Account, Account.id == Transaction.account_id)
        .options(selectinload(Transaction.category))
        .where(*filters)
        .order_by(Transaction.posted_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return TransactionList(
        items=[_to_read(t, name) for t, name in rows],
        page=Page(total=total, limit=limit, offset=offset),
    )


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    session: DbSession, user: CurrentUser, transaction_id: int, payload: TransactionUpdate
) -> TransactionRead:
    """Set a category by hand.

    Records `category_source='manual'`, which the rules engine treats as untouchable.
    That pairing is the whole reason the column exists: without it, the next rule run
    would quietly undo every correction a person made.
    """
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    _require_category(session, payload.category_id)

    transaction.category_id = payload.category_id
    # Clearing a category clears its provenance too: an uncategorised row with a
    # lingering 'manual' source would be invisible to the rules engine for ever.
    transaction.category_source = CategorySource.MANUAL if payload.category_id is not None else None
    session.flush()
    session.refresh(transaction)

    account = session.get(Account, transaction.account_id)
    return _to_read(transaction, account.name if account else "")


@router.post("/bulk-transfer", response_model=BulkTransferResult)
def bulk_transfer(
    session: DbSession, user: CurrentUser, payload: BulkTransfer
) -> BulkTransferResult:
    """Mark transactions as the two sides of one transfer, or unlink them.

    A pair needs both sides, so linking fewer than two is rejected rather than
    quietly creating a group of one — a lone "transfer" that pairs with nothing is
    indistinguishable from a mistake, and it changes no total either way.

    Unlinking accepts a single id, because breaking a bad pairing one side at a time
    is a reasonable thing to want.
    """
    if payload.linked and len(payload.transaction_ids) < 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer pair needs at least two transactions",
        )

    transactions = list(
        session.execute(
            select(Transaction).where(Transaction.id.in_(payload.transaction_ids))
        ).scalars()
    )

    group_id = uuid.uuid4().hex if payload.linked else None
    for transaction in transactions:
        transaction.transfer_group_id = group_id

    session.flush()
    return BulkTransferResult(transfer_group_id=group_id, updated=len(transactions))


@router.post("/bulk-categorise", response_model=BulkCategoriseResult)
def bulk_categorise(
    session: DbSession, user: CurrentUser, payload: BulkCategorise
) -> BulkCategoriseResult:
    """Categorise many at once — the same manual write, applied to a selection."""
    _require_category(session, payload.category_id)

    transactions = list(
        session.execute(
            select(Transaction).where(Transaction.id.in_(payload.transaction_ids))
        ).scalars()
    )

    for transaction in transactions:
        transaction.category_id = payload.category_id
        transaction.category_source = (
            CategorySource.MANUAL if payload.category_id is not None else None
        )

    session.flush()
    return BulkCategoriseResult(updated=len(transactions))
