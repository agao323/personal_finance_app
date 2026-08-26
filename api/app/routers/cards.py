"""Credit cards and the perks they carry.

`GET /perks/upcoming` is the endpoint this feature exists for. Everything else here is
data entry: a list of cards you had to read down to work out what expires this week
would be a worse version of the spreadsheet it replaces.

**The date is always a parameter, defaulting to today at the edge.** Nothing below reads
the clock, because every case worth testing is about a specific day — the one a period
rolls over on, the 29th of February — and a service that called `date.today()` could not
be asked about any of them.

Route docstrings are part of the frozen contract — see the note in `routers/rules.py`.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import AccountSubtype
from app.schemas.card_perk import (
    CardRead,
    PerkCreate,
    PerkPeriodRead,
    PerkRead,
    PerkUpdate,
    RedemptionCreate,
    UpcomingPerk,
    UpcomingRead,
)
from app.schemas.common import ErrorResponse, from_cents, to_cents
from app.services import perks as perk_service

router = APIRouter(tags=["cards"], responses={404: {"model": ErrorResponse}})

#: One message whether the account does not exist, is not a credit card, or belongs to
#: nobody. Which of those you hit is not a useful distinction to a caller and is a way
#: to enumerate accounts.
NO_CARD = "No such credit card"
NO_PERK = "No such perk"


def _card(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.subtype is not AccountSubtype.CREDIT_CARD:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_CARD)
    return account


def _perk(session: Session, perk_id: int) -> CardPerk:
    perk = session.get(CardPerk, perk_id)
    if perk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_PERK)
    return perk


def _redeemed(session: Session, perk_id: int, period_start: dt.date) -> PerkRedemption | None:
    return session.execute(
        select(PerkRedemption).where(
            PerkRedemption.perk_id == perk_id, PerkRedemption.period_start == period_start
        )
    ).scalar_one_or_none()


def _to_read(session: Session, perk: CardPerk, on: dt.date) -> PerkRead:
    """A perk with its current period resolved.

    The period comes from `services/perks.py` rather than being worked out here, so
    there is exactly one implementation of what window a date is in — the same rule that
    keeps rounding inside `services/ownership.py`.
    """
    period = perk_service.period_containing(perk.cadence, perk.anchor_on, on)
    current: PerkPeriodRead | None = None
    if period is not None:
        redemption = _redeemed(session, perk.id, period.start)
        current = PerkPeriodRead(
            start=period.start,
            end=period.end,
            days_remaining=period.days_remaining(on),
            is_used=redemption is not None,
            used_note=redemption.note if redemption else None,
        )
    return PerkRead(
        id=perk.id,
        account_id=perk.account_id,
        name=perk.name,
        description=perk.description,
        value_cents=to_cents(perk.value),
        cadence=perk.cadence,
        anchor_on=perk.anchor_on,
        is_active=perk.is_active,
        current_period=current,
    )


@router.get("/cards", response_model=list[CardRead])
def list_cards(
    session: DbSession,
    user: CurrentUser,
    on: Annotated[dt.date | None, Query(description="Evaluate periods as of this date.")] = None,
) -> list[CardRead]:
    """Every credit card account with its perks and their current periods."""
    today = on or dt.date.today()
    cards = session.execute(
        select(Account)
        .where(Account.subtype == AccountSubtype.CREDIT_CARD)
        .order_by(Account.name, Account.id)
    ).scalars()

    result: list[CardRead] = []
    for account in cards:
        rows = session.execute(
            select(CardPerk)
            .where(CardPerk.account_id == account.id)
            .order_by(CardPerk.is_active.desc(), CardPerk.name, CardPerk.id)
        ).scalars()
        perk_reads = [_to_read(session, perk, today) for perk in rows]
        unused = sum(
            p.value_cents
            for p in perk_reads
            if p.is_active and p.current_period is not None and not p.current_period.is_used
        )
        result.append(
            CardRead(
                account_id=account.id,
                name=account.name,
                institution=account.institution.name if account.institution else None,
                is_closed=account.closed_at is not None,
                perks=perk_reads,
                unused_cents=unused,
            )
        )
    return result


@router.post("/cards/{account_id}/perks", response_model=PerkRead, status_code=201)
def add_perk(
    session: DbSession, user: CurrentUser, account_id: int, payload: PerkCreate
) -> PerkRead:
    """Add a recurring benefit to a credit card."""
    account = _card(session, account_id)
    perk = CardPerk(
        account_id=account.id,
        name=payload.name,
        description=payload.description,
        value=from_cents(payload.value_cents),
        cadence=payload.cadence,
        anchor_on=payload.anchor_on,
    )
    session.add(perk)
    session.flush()
    return _to_read(session, perk, dt.date.today())


@router.patch("/perks/{perk_id}", response_model=PerkRead)
def update_perk(
    session: DbSession, user: CurrentUser, perk_id: int, payload: PerkUpdate
) -> PerkRead:
    """Edit a perk, or retire it by setting `is_active` false.

    Retiring rather than deleting: a perk the card stopped offering still has a
    redemption history, and removing it would rewrite what you did last year.
    """
    perk = _perk(session, perk_id)
    changes = payload.model_dump(exclude_unset=True)
    # `value_cents` is the wire name; the column is `value` and holds a Decimal. Popped
    # rather than special-cased inside the loop so there is no path where an integer
    # number of cents is assigned to a money column.
    if "value_cents" in changes:
        perk.value = from_cents(changes.pop("value_cents"))
    for field, value in changes.items():
        setattr(perk, field, value)
    session.flush()
    return _to_read(session, perk, dt.date.today())


@router.post("/perks/{perk_id}/redemptions", response_model=PerkRead)
def mark_used(
    session: DbSession, user: CurrentUser, perk_id: int, payload: RedemptionCreate
) -> PerkRead:
    """Mark the period containing `on` as used. Idempotent.

    Marking twice is not an error. This button gets pressed twice — on a phone, in a
    restaurant, when the first tap did not visibly do anything — and answering 409 to
    the second would be a worse outcome than the no-op it actually is.
    """
    perk = _perk(session, perk_id)
    on = payload.on or dt.date.today()
    period = perk_service.period_containing(perk.cadence, perk.anchor_on, on)
    if period is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That date is before this perk's first period",
        )

    existing = _redeemed(session, perk.id, period.start)
    if existing is None:
        session.add(PerkRedemption(perk_id=perk.id, period_start=period.start, note=payload.note))
    elif payload.note is not None:
        existing.note = payload.note
    session.flush()
    return _to_read(session, perk, on)


@router.delete("/perks/{perk_id}/redemptions", response_model=PerkRead)
def mark_unused(
    session: DbSession,
    user: CurrentUser,
    perk_id: int,
    on: Annotated[dt.date | None, Query()] = None,
) -> PerkRead:
    """Undo a mark. Idempotent — unmarking something already unused is a no-op."""
    perk = _perk(session, perk_id)
    day = on or dt.date.today()
    period = perk_service.period_containing(perk.cadence, perk.anchor_on, day)
    if period is not None:
        session.execute(
            delete(PerkRedemption).where(
                PerkRedemption.perk_id == perk.id,
                PerkRedemption.period_start == period.start,
            )
        )
        session.flush()
    return _to_read(session, perk, day)


@router.get("/perks/upcoming", response_model=UpcomingRead)
def upcoming(
    session: DbSession,
    user: CurrentUser,
    within_days: Annotated[int, Query(ge=0, le=366)] = 30,
    on: Annotated[dt.date | None, Query()] = None,
) -> UpcomingRead:
    """Unused perks whose current period ends within `within_days`, soonest first.

    The point of the feature. Closed cards are excluded — a perk on a card you no longer
    hold is not something you can still use.
    """
    today = on or dt.date.today()
    rows = session.execute(
        select(CardPerk, Account)
        .join(Account, Account.id == CardPerk.account_id)
        .where(
            CardPerk.is_active.is_(True),
            Account.subtype == AccountSubtype.CREDIT_CARD,
            Account.closed_at.is_(None),
        )
    ).all()

    found: list[tuple[int, UpcomingPerk]] = []
    for perk, account in rows:
        read = _to_read(session, perk, today)
        period = read.current_period
        if period is None or period.is_used or period.days_remaining > within_days:
            continue
        found.append(
            (
                period.days_remaining,
                UpcomingPerk(perk=read, account_id=account.id, card_name=account.name),
            )
        )

    # Soonest first, then by value: two perks expiring the same day are better read
    # with the expensive one at the top.
    found.sort(key=lambda pair: (pair[0], -pair[1].perk.value_cents, pair[1].perk.name))
    ordered = [item for _, item in found]

    return UpcomingRead(
        within_days=within_days,
        as_of=today,
        total_cents=sum(item.perk.value_cents for item in ordered),
        perks=ordered,
    )
