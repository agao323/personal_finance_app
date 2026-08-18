"""Accounts, ownership stakes, and balance entry."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.enums import AccountKind, DataSource
from app.models.user import User
from app.schemas.account import (
    AccountCreate,
    AccountDetail,
    AccountGroup,
    AccountHistory,
    AccountList,
    AccountRead,
    AccountUpdate,
    BalanceCreate,
    BalanceRead,
    InstitutionRead,
    StakeCreate,
    StakeRead,
)
from app.schemas.common import ErrorResponse, ViewScope, from_bps, to_bps, to_cents
from app.services.accounts import (
    AccountView,
    create_account,
    list_accounts,
    snapshot_history,
    stake_history,
    view_for,
)
from app.services.balances import record_balance
from app.services.ownership import OverlappingStakeError, transition_stake

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)

ZERO = Decimal("0.00")


def _viewer(view: ViewScope, user_id: int) -> int | None:
    return None if view is ViewScope.HOUSEHOLD else user_id


def _get(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


def _to_read(view: AccountView) -> AccountRead:
    account = view.account
    return AccountRead(
        id=account.id,
        name=account.name,
        kind=account.kind,
        subtype=account.subtype,
        source=account.source,
        currency=account.currency,
        closed_at=account.closed_at,
        institution=(
            None
            if account.institution is None
            else InstitutionRead(id=account.institution.id, name=account.institution.name)
        ),
        balance_cents=None if view.balance is None else to_cents(view.balance.balance),
        adjusted_balance_cents=(None if view.adjusted is None else to_cents(view.adjusted)),
        balance_as_of=None if view.balance is None else view.balance.as_of,
        is_stale=view.balance.is_stale if view.balance else False,
        current_stake_bps=None if view.percentage is None else to_bps(view.percentage),
    )


def _to_stake(session: Session, stake: object) -> StakeRead:
    owner = session.get(User, stake.owner_user_id)  # type: ignore[attr-defined]
    return StakeRead(
        id=stake.id,  # type: ignore[attr-defined]
        owner_user_id=stake.owner_user_id,  # type: ignore[attr-defined]
        owner_display_name=owner.display_name if owner else "Unknown",
        percentage_bps=to_bps(stake.percentage),  # type: ignore[attr-defined]
        effective_from=stake.effective_from,  # type: ignore[attr-defined]
        effective_to=stake.effective_to,  # type: ignore[attr-defined]
    )


@router.get("", response_model=AccountList)
def list_all(
    session: DbSession,
    user: CurrentUser,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
    include_closed: Annotated[bool, Query()] = False,
    as_of: Annotated[dt.date | None, Query()] = None,
) -> AccountList:
    """Accounts grouped by kind, with raw and ownership-adjusted subtotals.

    Both values are exposed deliberately. A 50%-owned rental should visibly show the
    full property value and your share — that distinction is the feature, and showing
    only one of them throws it away.
    """
    when = as_of or dt.date.today()
    views = list_accounts(session, when, _viewer(view, user.id), include_closed)

    groups: list[AccountGroup] = []
    for kind in AccountKind:
        members = [v for v in views if v.account.kind is kind]
        if not members:
            continue
        groups.append(
            AccountGroup(
                kind=kind,
                accounts=[_to_read(v) for v in members],
                total_cents=to_cents(sum((v.balance.balance for v in members if v.balance), ZERO)),
                adjusted_total_cents=to_cents(
                    sum((v.adjusted for v in members if v.adjusted is not None), ZERO)
                ),
            )
        )

    return AccountList(
        groups=groups,
        total_cents=sum(g.total_cents for g in groups),
        adjusted_total_cents=sum(g.adjusted_total_cents for g in groups),
    )


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create(session: DbSession, user: CurrentUser, payload: AccountCreate) -> AccountRead:
    """Create an account, its explicit 100% stake, and any opening balance.

    All in one transaction. An account with no stake row contributes to no net worth
    figure, so a partial success would create something that exists and is
    simultaneously invisible.
    """
    account = create_account(
        session,
        name=payload.name,
        kind=payload.kind,
        subtype=payload.subtype,
        owner_user_id=payload.owner_user_id or user.id,
        institution_id=payload.institution_id,
        institution_name=payload.institution_name,
        source=payload.source,
        ownership_percentage=(
            None
            if payload.ownership_percentage_bps is None
            else from_bps(payload.ownership_percentage_bps)
        ),
        opening_balance=(
            None
            if payload.opening_balance_cents is None
            else Decimal(payload.opening_balance_cents) / 100
        ),
        opening_balance_as_of=payload.opening_balance_as_of,
    )
    return _to_read(view_for(session, account, dt.date.today(), user.id))


@router.get("/{account_id}", response_model=AccountDetail)
def detail(
    session: DbSession,
    user: CurrentUser,
    account_id: int,
    view: Annotated[ViewScope, Query()] = ViewScope.MINE,
) -> AccountDetail:
    account = _get(session, account_id)
    resolved = view_for(session, account, dt.date.today(), _viewer(view, user.id))
    base = _to_read(resolved)

    return AccountDetail(
        **base.model_dump(),
        stakes=[_to_stake(session, s) for s in stake_history(session, account_id)],
    )


@router.patch("/{account_id}", response_model=AccountRead)
def update(
    session: DbSession, user: CurrentUser, account_id: int, payload: AccountUpdate
) -> AccountRead:
    """Rename, re-file, or close an account.

    Closing is a date, not a deletion: the history stays intact and net worth simply
    stops counting it from that day — see docs/ARCHITECTURE.md#data-model.
    """
    account = _get(session, account_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    session.flush()

    return _to_read(view_for(session, account, dt.date.today(), user.id))


@router.get("/{account_id}/history", response_model=AccountHistory)
def history(session: DbSession, user: CurrentUser, account_id: int) -> AccountHistory:
    _get(session, account_id)
    return AccountHistory(
        account_id=account_id,
        points=[
            BalanceRead(
                as_of=s.as_of,
                balance_cents=to_cents(s.balance),
                source=s.source,
                # A recorded snapshot is by definition fresh on its own date; staleness
                # is a property of carrying one forward, not of the row itself.
                is_stale=False,
            )
            for s in snapshot_history(session, account_id)
        ],
    )


@router.post(
    "/{account_id}/balances", response_model=BalanceRead, status_code=status.HTTP_201_CREATED
)
def add_balance(
    session: DbSession, user: CurrentUser, account_id: int, payload: BalanceCreate
) -> BalanceRead:
    """Record a snapshot. Re-recording the same date replaces the value."""
    _get(session, account_id)

    snapshot = record_balance(
        session,
        account_id,
        payload.as_of,
        Decimal(payload.balance_cents) / 100,
        payload.source or DataSource.MANUAL,
    )
    return BalanceRead(
        as_of=snapshot.as_of,
        balance_cents=to_cents(snapshot.balance),
        source=snapshot.source,
        is_stale=False,
    )


@router.post("/{account_id}/stakes", response_model=StakeRead, status_code=status.HTTP_201_CREATED)
def set_stake(
    session: DbSession, user: CurrentUser, account_id: int, payload: StakeCreate
) -> StakeRead:
    """Close the stake in force and open a new one, atomically.

    Historical net worth is untouched: the old row is closed on the new row's start
    date rather than edited, so every figure before that date still reads the old
    percentage.
    """
    _get(session, account_id)

    try:
        stake = transition_stake(
            session,
            account_id,
            payload.owner_user_id,
            from_bps(payload.percentage_bps),
            payload.effective_from,
        )
    except OverlappingStakeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return _to_stake(session, stake)
