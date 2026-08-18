"""Transactions and manual categorisation. Implemented by ticket 023."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.common import ErrorResponse
from app.schemas.transaction import (
    BulkCategorise,
    BulkCategoriseResult,
    TransactionList,
    TransactionRead,
    TransactionUpdate,
)

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


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
    not_implemented("023")


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    session: DbSession, user: CurrentUser, transaction_id: int, payload: TransactionUpdate
) -> TransactionRead:
    """Sets category_source='manual', which the rules engine never overwrites."""
    not_implemented("023")


@router.post("/bulk-categorise", response_model=BulkCategoriseResult)
def bulk_categorise(
    session: DbSession, user: CurrentUser, payload: BulkCategorise
) -> BulkCategoriseResult:
    not_implemented("023")
