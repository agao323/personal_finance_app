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

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import AccountSubtype, PerkCadence
from app.schemas.card_perk import (
    CardRead,
    HistoryRead,
    PerkCreate,
    PerkPeriodRead,
    PerkPeriodsRead,
    PerkPeriodState,
    PerkRead,
    PerkScheduleRead,
    PerkUpdate,
    RedemptionCreate,
    RedemptionRead,
    UpcomingPerk,
    UpcomingRead,
)
from app.schemas.common import ErrorResponse, from_cents, to_cents
from app.services import cards as card_service
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


def _to_read(view: card_service.PerkView) -> PerkRead:
    """Map a resolved perk to the wire. The reading itself is `services/cards.perk_view`."""
    perk, current = view.perk, view.current
    return PerkRead(
        id=perk.id,
        account_id=perk.account_id,
        name=perk.name,
        description=perk.description,
        value_cents=to_cents(perk.value),
        cadence=perk.cadence,
        anchor_on=perk.anchor_on,
        is_active=perk.is_active,
        current_period=(
            None
            if current is None
            else PerkPeriodRead(
                start=current.start,
                end=current.end,
                days_remaining=current.days_remaining,
                is_used=current.is_used,
                used_note=current.used_note,
                used_amount_cents=(
                    to_cents(current.used_amount) if current.used_amount is not None else None
                ),
                is_urgent=current.is_urgent,
            )
        ),
    )


def _read(session: Session, perk: CardPerk, on: dt.date) -> PerkRead:
    return _to_read(card_service.perk_view(session, perk, on))


@router.get("/cards", response_model=list[CardRead])
def list_cards(
    session: DbSession,
    user: CurrentUser,
    on: Annotated[dt.date | None, Query(description="Evaluate periods as of this date.")] = None,
) -> list[CardRead]:
    """Every credit card account with its perks and their current periods."""
    return [
        CardRead(
            account_id=card.account.id,
            name=card.account.name,
            institution=card.account.institution.name if card.account.institution else None,
            is_closed=card.account.closed_at is not None,
            perks=[_to_read(view) for view in card.perks],
            unused_cents=to_cents(card.unused),
            active_perk_count=card.active_perk_count,
            annual_fee_cents=(
                to_cents(card.account.annual_fee) if card.account.annual_fee is not None else None
            ),
            fee_renews_on=card.account.fee_renews_on,
            realised_this_year_cents=to_cents(card.realised_this_year),
        )
        for card in card_service.list_cards(session, on or dt.date.today())
    ]


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
    return _read(session, perk, dt.date.today())


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
    return _read(session, perk, dt.date.today())


@router.delete("/perks/{perk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_perk(session: DbSession, user: CurrentUser, perk_id: int) -> Response:
    """Remove a perk entirely — refused with 409 once it has any history.

    Two different actions that look alike. **Delete** is for the perk you added by
    mistake. **Retire** (`PATCH` with `is_active: false`) is for one the card stopped
    offering, and it keeps the redemptions that record what you actually used. Deleting a
    used perk would erase that, so it is refused rather than cascading.
    """
    perk = _perk(session, perk_id)
    recorded = session.execute(
        select(func.count()).select_from(PerkRedemption).where(PerkRedemption.perk_id == perk.id)
    ).scalar_one()
    if recorded:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"That perk has {recorded} recorded use"
                f"{'' if recorded == 1 else 's'}. Retire it instead, which keeps the "
                "history."
            ),
        )
    session.delete(perk)
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # Any date resolves to a period, including one before the anchor. See ticket 076: the
    # anchor sets where a boundary falls, not when the credit came into existence, and
    # refusing a backfill on that basis refused uses there was no reason to doubt.
    period = perk_service.period_containing(perk.cadence, perk.anchor_on, on)

    amount = from_cents(payload.amount_cents) if payload.amount_cents is not None else None
    existing = card_service.redemption_for(session, perk.id, period.start)
    if existing is None:
        session.add(
            PerkRedemption(
                perk_id=perk.id,
                period_start=period.start,
                amount=amount,
                note=payload.note,
            )
        )
    else:
        # A second mark **updates** rather than erroring. Correcting "I used all of it"
        # to "I used $50 of it" is a re-mark, not a conflict.
        if payload.amount_cents is not None:
            existing.amount = amount
        if payload.note is not None:
            existing.note = payload.note
    session.flush()
    return _read(session, perk, on)


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
    session.execute(
        delete(PerkRedemption).where(
            PerkRedemption.perk_id == perk.id,
            PerkRedemption.period_start == period.start,
        )
    )
    session.flush()
    return _read(session, perk, day)


def _history(
    session: Session,
    *,
    perk_id: int | None,
    account_id: int | None = None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    today: dt.date,
) -> HistoryRead:
    """Map `services/cards.history` to the wire."""
    result = card_service.history(
        session,
        perk_id=perk_id,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        today=today,
    )
    return HistoryRead(
        from_date=result.from_date,
        to_date=result.to_date,
        realised_cents=to_cents(result.realised),
        missed_periods=result.missed_periods,
        redemptions=[
            RedemptionRead(
                perk_id=entry.perk.id,
                perk_name=entry.perk.name,
                account_id=entry.account.id,
                card_name=entry.account.name,
                period_start=entry.redemption.period_start,
                period_end=entry.period_end,
                cadence=entry.perk.cadence,
                realised_cents=to_cents(entry.realised),
                is_face_value=entry.redemption.amount is None,
                note=entry.redemption.note,
                recorded_at=entry.redemption.created_at,
            )
            for entry in result.entries
        ],
    )


@router.get("/cards/history", response_model=HistoryRead)
def wallet_history(
    session: DbSession,
    user: CurrentUser,
    from_date: Annotated[dt.date | None, Query(alias="from")] = None,
    to_date: Annotated[dt.date | None, Query(alias="to")] = None,
    account_id: Annotated[int | None, Query()] = None,
    on: Annotated[dt.date | None, Query()] = None,
) -> HistoryRead:
    """Every redemption, newest first — across the wallet, or for one card.

    **No default window.** The request this answers is "show me everything I have ever
    marked", and a silent cut-off would hide exactly the old entries being asked for.

    `account_id` scopes it to one card. Filtering in the browser would work today and grow
    without bound, and `missed_periods` could not be filtered that way at all — it is
    counted by walking each perk's periods, not derived from the rows returned.
    """
    return _history(
        session,
        perk_id=None,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        today=on or dt.date.today(),
    )


@router.get("/perks/{perk_id}/history", response_model=HistoryRead)
def perk_history(
    session: DbSession,
    user: CurrentUser,
    perk_id: int,
    from_date: Annotated[dt.date | None, Query(alias="from")] = None,
    to_date: Annotated[dt.date | None, Query(alias="to")] = None,
    on: Annotated[dt.date | None, Query()] = None,
) -> HistoryRead:
    """One perk's history, first recorded use to most recent."""
    _perk(session, perk_id)
    return _history(
        session, perk_id=perk_id, from_date=from_date, to_date=to_date, today=on or dt.date.today()
    )


#: How many upcoming resets the schedule preview reports.
#:
#: Four, because that is enough to show the shape at every cadence — a year of quarters, a
#: third of a year of months — without the form growing a list nobody reads.
SCHEDULE_AHEAD = 4


@router.get("/perks/schedule", response_model=PerkScheduleRead)
def perk_schedule(
    session: DbSession,
    user: CurrentUser,
    cadence: Annotated[PerkCadence, Query()],
    anchor_on: Annotated[dt.date, Query()],
    on: Annotated[dt.date | None, Query()] = None,
) -> PerkScheduleRead:
    """What a cadence and an anchor would produce, for a credit that does not exist yet.

    Reads nothing and writes nothing. It exists so the form that sets an anchor can show what
    the anchor does before it is saved: anchored 1 September a quarterly credit genuinely
    resets on 1 December, which is correct arithmetic and almost never what was meant.
    """
    today = on or dt.date.today()
    current = perk_service.period_containing(cadence, anchor_on, today)
    return PerkScheduleRead(
        cadence=cadence,
        anchor_on=anchor_on,
        is_calendar_aligned=perk_service.is_calendar_aligned(cadence, anchor_on),
        current_start=current.start,
        resets_on=[
            perk_service.period_at(cadence, anchor_on, current.index + step).end
            for step in range(SCHEDULE_AHEAD)
        ],
    )


@router.get("/perks/{perk_id}/periods", response_model=PerkPeriodsRead)
def perk_periods(
    session: DbSession,
    user: CurrentUser,
    perk_id: int,
    back: Annotated[
        int, Query(ge=1, le=60, description="How many periods to return, counting back.")
    ] = 12,
    on: Annotated[dt.date | None, Query()] = None,
) -> PerkPeriodsRead:
    """This perk's recent periods, oldest first, each with whether it was used.

    What the screen needs to ask "which months did you use this?" instead of asking for a
    date and then explaining which period that date lands in. The periods come from
    `services/perks.py`, so the windows offered are the same windows a mark resolves to.

    `back` is a count of periods, not a span of days, because how much history is worth
    showing is a per-cadence question: twelve months and twelve years are both twelve
    chips, and the caller is the one that knows which it wants.
    """
    perk = _perk(session, perk_id)
    today = on or dt.date.today()
    windows = perk_service.recent_periods(perk.cadence, perk.anchor_on, today, back)

    marked: dict[dt.date, PerkRedemption] = {}
    if windows:
        # One query for the whole range, not one per period. `period_start` is indexed by
        # the unique constraint on (perk_id, period_start).
        marked = {
            row.period_start: row
            for row in session.execute(
                select(PerkRedemption).where(
                    PerkRedemption.perk_id == perk.id,
                    PerkRedemption.period_start >= windows[0].start,
                    PerkRedemption.period_start <= windows[-1].start,
                )
            ).scalars()
        }

    states: list[PerkPeriodState] = []
    for window in windows:
        redemption = marked.get(window.start)
        states.append(
            PerkPeriodState(
                start=window.start,
                end=window.end,
                index=window.index,
                is_used=redemption is not None,
                used_amount_cents=(
                    to_cents(redemption.amount)
                    if redemption is not None and redemption.amount is not None
                    else None
                ),
                note=redemption.note if redemption is not None else None,
                # The last window is the one containing `today`, by construction.
                is_current=window.index == windows[-1].index,
            )
        )

    return PerkPeriodsRead(
        perk_id=perk.id,
        cadence=perk.cadence,
        anchor_on=perk.anchor_on,
        # Always true since ticket 076: the anchor is not a start date, so there is no
        # first period. What ends "show earlier" is the client's own cap on `back`.
        has_earlier=bool(windows),
        periods=states,
    )


@router.get("/perks/upcoming", response_model=UpcomingRead)
def upcoming(
    session: DbSession,
    user: CurrentUser,
    within_days: Annotated[int, Query(ge=0, le=366)] = 90,
    on: Annotated[dt.date | None, Query()] = None,
) -> UpcomingRead:
    """Unused perks whose current period ends within `within_days`, soonest first.

    The point of the feature. Closed cards are excluded — a perk on a card you no longer
    hold is not something you can still use.
    """
    result = card_service.upcoming(session, within_days, on or dt.date.today())
    return UpcomingRead(
        within_days=result.within_days,
        as_of=result.as_of,
        total_cents=to_cents(result.total),
        urgent_cents=to_cents(result.urgent),
        perks=[
            UpcomingPerk(
                perk=_to_read(item.view), account_id=item.account.id, card_name=item.account.name
            )
            for item in result.items
        ],
    )
