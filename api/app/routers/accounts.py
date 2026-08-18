"""Accounts, stakes, and balance entry. Implemented by ticket 019."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.account import (
    AccountCreate,
    AccountDetail,
    AccountHistory,
    AccountList,
    AccountRead,
    AccountUpdate,
    BalanceCreate,
    BalanceRead,
    StakeCreate,
    StakeRead,
)
from app.schemas.common import ErrorResponse, ViewScope

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


@router.get("", response_model=AccountList)
def list_accounts(
    session: DbSession,
    user: CurrentUser,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
    include_closed: Annotated[bool, Query()] = False,
) -> AccountList:
    not_implemented("019")


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(session: DbSession, user: CurrentUser, payload: AccountCreate) -> AccountRead:
    not_implemented("019")


@router.get("/{account_id}", response_model=AccountDetail)
def get_account(session: DbSession, user: CurrentUser, account_id: int) -> AccountDetail:
    not_implemented("019")


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    session: DbSession, user: CurrentUser, account_id: int, payload: AccountUpdate
) -> AccountRead:
    not_implemented("019")


@router.get("/{account_id}/history", response_model=AccountHistory)
def get_account_history(session: DbSession, user: CurrentUser, account_id: int) -> AccountHistory:
    not_implemented("019")


@router.post(
    "/{account_id}/balances", response_model=BalanceRead, status_code=status.HTTP_201_CREATED
)
def record_account_balance(
    session: DbSession, user: CurrentUser, account_id: int, payload: BalanceCreate
) -> BalanceRead:
    not_implemented("019")


@router.post("/{account_id}/stakes", response_model=StakeRead, status_code=status.HTTP_201_CREATED)
def set_account_stake(
    session: DbSession, user: CurrentUser, account_id: int, payload: StakeCreate
) -> StakeRead:
    """Closes the stake in force and opens a new one. See services/ownership.py."""
    not_implemented("019")
