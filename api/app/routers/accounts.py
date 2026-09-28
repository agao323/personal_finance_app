"""Accounts, ownership stakes, and balance entry."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.enums import AccountKind, DataSource
from app.models.liability_terms import LiabilityTerms
from app.models.user import User
from app.schemas.account import (
    AccountCreate,
    AccountDelete,
    AccountDetail,
    AccountGroup,
    AccountHistory,
    AccountList,
    AccountRead,
    AccountUpdate,
    BalanceCreate,
    BalanceRead,
    DeletionPreview,
    InstitutionRead,
    LiabilityTermsRead,
    LiabilityTermsUpdate,
    StakeCreate,
    StakeRead,
)
from app.schemas.common import ErrorResponse, ViewScope, from_bps, from_cents, to_bps, to_cents
from app.services import liability_terms as terms_service
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

    changes = payload.model_dump(exclude_unset=True)
    # `annual_fee_cents` is the wire name; the column is `annual_fee` and holds a Decimal.
    # Popped rather than special-cased in the loop, so no path assigns an integer number of
    # cents to a money column.
    if "annual_fee_cents" in changes:
        cents = changes.pop("annual_fee_cents")
        account.annual_fee = None if cents is None else from_cents(cents)
    for field, value in changes.items():
        setattr(account, field, value)
    session.flush()

    return _to_read(view_for(session, account, dt.date.today(), user.id))


@router.get("/{account_id}/deletion-preview", response_model=DeletionPreview)
def deletion_preview(session: DbSession, user: CurrentUser, account_id: int) -> DeletionPreview:
    """Exactly what deleting this account would destroy.

    Every child of `accounts` is `ON DELETE CASCADE`, so this is not a list of things to
    tidy afterwards — it is what disappears in the same statement. Counted from the
    database rather than estimated, because a warning with a wrong number is worse than a
    vague one: it teaches you the numbers are decorative.
    """
    account = _get(session, account_id)

    def count(sql: str) -> int:
        return int(session.execute(text(sql), {"a": account_id}).scalar_one())

    return DeletionPreview(
        account_id=account.id,
        name=account.name,
        balance_snapshots=count("SELECT count(*) FROM balance_snapshots WHERE account_id = :a"),
        transactions=count("SELECT count(*) FROM transactions WHERE account_id = :a"),
        ownership_stakes=count("SELECT count(*) FROM ownership_stakes WHERE account_id = :a"),
        card_perks=count("SELECT count(*) FROM card_perks WHERE account_id = :a"),
        perk_redemptions=count(
            "SELECT count(*) FROM perk_redemptions r JOIN card_perks p ON p.id = r.perk_id "
            "WHERE p.account_id = :a"
        ),
        earliest_snapshot=session.execute(
            text("SELECT min(as_of) FROM balance_snapshots WHERE account_id = :a"),
            {"a": account_id},
        ).scalar_one_or_none(),
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    session: DbSession, user: CurrentUser, account_id: int, payload: AccountDelete
) -> Response:
    """Delete an account and everything hanging off it.

    **This is the most destructive action in the product.** The cascade takes ownership
    stakes, balance snapshots, transactions, import mappings, card perks and every
    redemption recorded against them. Balance snapshots are the one class of data here that
    cannot be reconstructed from a bank, and ticket 017 is not done — there is no backup to
    restore from.

    Closing an account (`PATCH` with `closed_at`) is what most people actually want: net
    worth stops counting it from that date and the history survives.

    Naming the account is required, and checked here rather than only in a dialog — a guard
    that lives in one component is a guard that a second caller does not have.
    """
    account = _get(session, account_id)
    if payload.confirm_name.strip() != account.name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f'To delete this account, confirm its name exactly: "{account.name}"',
        )
    session.delete(account)
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


# ── liability terms (ticket 112) ──────────────────────────────────────────────


def _thousandths(pct: Decimal) -> int:
    return int(pct.scaleb(3))


def _from_thousandths(value: int) -> Decimal:
    return Decimal(value).scaleb(-3)


def _terms_read(terms: LiabilityTerms, today: dt.date) -> LiabilityTermsRead:
    return LiabilityTermsRead(
        account_id=terms.account_id,
        apr_pct_thousandths=_thousandths(terms.apr),
        effective_apr_pct_thousandths=_thousandths(terms_service.effective_apr(terms, today)),
        minimum_payment_cents=(
            to_cents(terms.minimum_payment) if terms.minimum_payment is not None else None
        ),
        credit_limit_cents=to_cents(terms.credit_limit) if terms.credit_limit is not None else None,
        term_months=terms.term_months,
        maturity_on=terms.maturity_on,
        promo_apr_pct_thousandths=(
            _thousandths(terms.promo_apr) if terms.promo_apr is not None else None
        ),
        promo_ends_on=terms.promo_ends_on,
        as_of=terms.as_of,
        stale=terms_service.is_stale(terms, today),
    )


@router.get("/{account_id}/terms", response_model=LiabilityTermsRead | None)
def get_terms(session: DbSession, user: CurrentUser, account_id: int) -> LiabilityTermsRead | None:
    """A loan's or card's rate, minimum payment and limit. Null until they are recorded."""
    _get(session, account_id)
    terms = terms_service.get(session, account_id)
    return None if terms is None else _terms_read(terms, dt.date.today())


@router.put("/{account_id}/terms", response_model=LiabilityTermsRead)
def put_terms(
    session: DbSession, user: CurrentUser, account_id: int, payload: LiabilityTermsUpdate
) -> LiabilityTermsRead:
    """Record a liability's terms. Only loans and cards have them."""
    account = _get(session, account_id)
    try:
        terms_service.require_liability(account)
    except terms_service.NotALiabilityError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    today = dt.date.today()
    terms = terms_service.get(session, account_id)
    if terms is None:
        terms = LiabilityTerms(account_id=account_id)
        session.add(terms)
    terms.apr = _from_thousandths(payload.apr_pct_thousandths)
    terms.minimum_payment = (
        Decimal(payload.minimum_payment_cents).scaleb(-2)
        if payload.minimum_payment_cents is not None
        else None
    )
    terms.credit_limit = (
        Decimal(payload.credit_limit_cents).scaleb(-2)
        if payload.credit_limit_cents is not None
        else None
    )
    terms.term_months = payload.term_months
    terms.maturity_on = payload.maturity_on
    terms.promo_apr = (
        _from_thousandths(payload.promo_apr_pct_thousandths)
        if payload.promo_apr_pct_thousandths is not None
        else None
    )
    terms.promo_ends_on = payload.promo_ends_on
    terms.as_of = payload.as_of or today
    session.flush()
    return _terms_read(terms, today)
