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
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import AccountSubtype
from app.schemas.card_perk import (
    CardRead,
    HistoryRead,
    PerkCreate,
    PerkPeriodRead,
    PerkPeriodsRead,
    PerkPeriodState,
    PerkRead,
    PerkUpdate,
    RedemptionCreate,
    RedemptionRead,
    UpcomingPerk,
    UpcomingRead,
)
from app.schemas.common import ErrorResponse, from_cents, to_cents
from app.services import perks as perk_service

#: Money accumulator start. Decimal, never float.
ZERO = Decimal("0.00")

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
        remaining = period.days_remaining(on)
        current = PerkPeriodRead(
            start=period.start,
            end=period.end,
            days_remaining=remaining,
            is_used=redemption is not None,
            used_note=redemption.note if redemption else None,
            used_amount_cents=(
                to_cents(redemption.amount)
                if redemption is not None and redemption.amount is not None
                else None
            ),
            # From the service, never recomputed here and never in the browser.
            is_urgent=perk_service.is_urgent(perk.cadence, remaining),
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
                active_perk_count=sum(1 for p in perk_reads if p.is_active),
                annual_fee_cents=(
                    to_cents(account.annual_fee) if account.annual_fee is not None else None
                ),
                fee_renews_on=account.fee_renews_on,
                realised_this_year_cents=_realised_this_year(session, account.id, today),
            )
        )
    return result


def _realised_value(redemption: PerkRedemption, perk: CardPerk) -> Decimal:
    """What one recorded use was worth.

    The recorded amount, or the perk's face value when a one-tap mark recorded none.
    **Never what was available**, which would flatter every card.

    One function because two callers need the same answer: the per-card figure and the
    history panel. They used to compute it separately and with different window rules, and
    the card screen showed both at once.
    """
    return redemption.amount if redemption.amount is not None else perk.value


def _realised_this_year(session: Session, account_id: int, on: dt.date) -> int:
    """Value realised on this card in the calendar year containing `on`, in cents.

    **Containment on `period_start`, the same rule `_history` applies** — a period belongs
    to the year it began in, and to exactly one year. That is what lets this figure and the
    history panel's "This year" window agree by construction rather than by comment.

    This replaced a fee year anchored on the renewal date, which matched on period
    *overlap* because a calendar-year credit's period almost always begins before the fee
    year it was counted against. The cost of overlap was that on the second day of a new
    fee year, a credit spent eleven months earlier still counted toward the fee just
    charged — wrong in exactly the case the figure existed for. See ticket 073.
    """
    start = dt.date(on.year, 1, 1)
    rows = session.execute(
        select(PerkRedemption, CardPerk)
        .join(CardPerk, CardPerk.id == PerkRedemption.perk_id)
        .where(
            CardPerk.account_id == account_id,
            PerkRedemption.period_start >= start,
            PerkRedemption.period_start <= on,
        )
    ).all()
    return to_cents(sum((_realised_value(r, p) for r, p in rows), ZERO))


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
    period = perk_service.period_containing(perk.cadence, perk.anchor_on, on)
    if period is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That date is before this perk's first period",
        )

    amount = from_cents(payload.amount_cents) if payload.amount_cents is not None else None
    existing = _redeemed(session, perk.id, period.start)
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


def _history(
    session: Session,
    *,
    perk_id: int | None,
    account_id: int | None = None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    today: dt.date,
) -> HistoryRead:
    """Recorded redemptions, newest first, with the value each realised.

    One implementation for both the per-perk and whole-wallet views: the only difference
    is a filter, and two copies would drift on the `missed_periods` arithmetic, which is
    the fiddly part.
    """
    query = (
        select(PerkRedemption, CardPerk, Account)
        .join(CardPerk, CardPerk.id == PerkRedemption.perk_id)
        .join(Account, Account.id == CardPerk.account_id)
    )
    if perk_id is not None:
        query = query.where(CardPerk.id == perk_id)
    if account_id is not None:
        query = query.where(CardPerk.account_id == account_id)
    if from_date is not None:
        query = query.where(PerkRedemption.period_start >= from_date)
    if to_date is not None:
        query = query.where(PerkRedemption.period_start <= to_date)

    rows = list(session.execute(query.order_by(PerkRedemption.period_start.desc())).all())

    entries: list[RedemptionRead] = []
    realised = ZERO
    for redemption, perk, account in rows:
        period = perk_service.period_containing(
            perk.cadence, perk.anchor_on, redemption.period_start
        )
        value = _realised_value(redemption, perk)
        realised += value
        entries.append(
            RedemptionRead(
                perk_id=perk.id,
                perk_name=perk.name,
                account_id=account.id,
                card_name=account.name,
                period_start=redemption.period_start,
                # A stored period_start always resolves, but fall back rather than
                # raising: a perk whose anchor was edited later must not break history.
                period_end=period.end if period else redemption.period_start,
                cadence=perk.cadence,
                realised_cents=to_cents(value),
                is_face_value=redemption.amount is None,
                note=redemption.note,
                recorded_at=redemption.created_at,
            )
        )

    # Periods that closed inside the window with nothing against them. Counted by
    # walking each perk's periods rather than inferred from a count, because a perk's
    # cadence determines how many periods a span even contains.
    missed = 0
    perks_query = select(CardPerk).where(CardPerk.is_active.is_(True))
    if perk_id is not None:
        perks_query = perks_query.where(CardPerk.id == perk_id)
    if account_id is not None:
        perks_query = perks_query.where(CardPerk.account_id == account_id)
    for perk in session.execute(perks_query).scalars():
        recorded = {
            row.period_start
            for row in session.execute(
                select(PerkRedemption).where(PerkRedemption.perk_id == perk.id)
            ).scalars()
        }
        cursor = max(perk.anchor_on, from_date) if from_date else perk.anchor_on
        horizon = min(to_date, today) if to_date else today
        while cursor <= horizon:
            period = perk_service.period_containing(perk.cadence, perk.anchor_on, cursor)
            if period is None:
                break
            # Only periods that have actually ended can be called missed. The current one
            # is still spendable.
            if period.end <= today and period.start not in recorded:
                missed += 1
            cursor = period.end

    return HistoryRead(
        from_date=from_date,
        to_date=to_date,
        realised_cents=to_cents(realised),
        missed_periods=missed,
        redemptions=entries,
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
        has_earlier=bool(windows) and windows[0].index > 0,
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
        urgent_cents=sum(
            item.perk.value_cents
            for item in ordered
            if item.perk.current_period is not None and item.perk.current_period.is_urgent
        ),
        perks=ordered,
    )
