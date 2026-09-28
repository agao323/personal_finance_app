"""Reading credit cards and their perks: current periods, what was realised, what is due.

Moved out of `routers/cards.py` by ticket 082 so that the Cards screen and the advisor's
card tools call **one** implementation. Two readings of "what did this card return this
year" would agree until the first time either changed, and the symptom would be the chat
telling you something the screen does not.

Everything here returns plain dataclasses with `Decimal` money; the router maps them to
the wire schemas. **Nothing here reads the clock** — every function takes the date to
evaluate, for the reason `services/perks.py` gives.

**None of this is net worth.** An unused credit is not money you have, and nothing here
may be summed into a balance — see `models/card_perk.py`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.card_perk import CardPerk, PerkRedemption
from app.models.enums import AccountSubtype
from app.services import perks as perk_service

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class CurrentPeriod:
    """The period a perk is in on a given day, and whether it has been used."""

    start: dt.date
    end: dt.date
    days_remaining: int
    is_used: bool
    used_note: str | None
    #: The recorded partial amount; `None` for a one-tap mark (full face value) or unused.
    used_amount: Decimal | None
    is_urgent: bool


@dataclass(frozen=True)
class PerkView:
    perk: CardPerk
    #: `None` while the perk's first period is still in the future.
    current: CurrentPeriod | None

    @property
    def is_unused_now(self) -> bool:
        return self.perk.is_active and self.current is not None and not self.current.is_used


@dataclass(frozen=True)
class CardView:
    account: Account
    perks: list[PerkView]
    #: Face value of active perks whose current period is unused.
    unused: Decimal
    active_perk_count: int
    realised_this_year: Decimal


@dataclass(frozen=True)
class RedemptionEntry:
    redemption: PerkRedemption
    perk: CardPerk
    account: Account
    period_end: dt.date
    realised: Decimal


@dataclass(frozen=True)
class History:
    from_date: dt.date | None
    to_date: dt.date | None
    realised: Decimal
    missed_periods: int
    #: Newest first.
    entries: list[RedemptionEntry]


@dataclass(frozen=True)
class UpcomingItem:
    view: PerkView
    account: Account


@dataclass(frozen=True)
class Upcoming:
    within_days: int
    as_of: dt.date
    total: Decimal
    urgent: Decimal
    #: Soonest first, then the more valuable of two ending the same day.
    items: list[UpcomingItem]


def redemption_for(session: Session, perk_id: int, period_start: dt.date) -> PerkRedemption | None:
    """The mark recorded for one period of one perk, if any."""
    return session.execute(
        select(PerkRedemption).where(
            PerkRedemption.perk_id == perk_id, PerkRedemption.period_start == period_start
        )
    ).scalar_one_or_none()


def perk_view(session: Session, perk: CardPerk, on: dt.date) -> PerkView:
    """A perk with its current period resolved.

    The period comes from `services/perks.py` rather than being worked out here, so
    there is exactly one implementation of what window a date is in — the same rule that
    keeps rounding inside `services/ownership.py`.
    """
    # **The one thing the anchor still gates**: a credit whose first period is in the future
    # has no current period. Asked here, as one comparison that says what it means, rather
    # than by `period_containing` answering None to two different questions (ticket 076).
    if perk.anchor_on > on:
        return PerkView(perk=perk, current=None)

    period = perk_service.period_containing(perk.cadence, perk.anchor_on, on)
    redemption = redemption_for(session, perk.id, period.start)
    remaining = period.days_remaining(on)
    return PerkView(
        perk=perk,
        current=CurrentPeriod(
            start=period.start,
            end=period.end,
            days_remaining=remaining,
            is_used=redemption is not None,
            used_note=redemption.note if redemption else None,
            used_amount=redemption.amount if redemption is not None else None,
            # From the service, never recomputed by a caller and never in the browser.
            is_urgent=perk_service.is_urgent(perk.cadence, remaining),
        ),
    )


def realised_value(redemption: PerkRedemption, perk: CardPerk) -> Decimal:
    """What one recorded use was worth.

    The recorded amount, or the perk's face value when a one-tap mark recorded none.
    **Never what was available**, which would flatter every card.

    One function because every caller needs the same answer: the per-card figure, the
    history panel, and the advisor's card value. They used to compute it separately and
    with different window rules, and the card screen showed both at once.
    """
    return redemption.amount if redemption.amount is not None else perk.value


def realised_this_year(session: Session, account_id: int, on: dt.date) -> Decimal:
    """Value realised on this card in the calendar year containing `on`.

    **Containment on `period_start`, the same rule `history` applies** — a period belongs
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
    return sum((realised_value(r, p) for r, p in rows), ZERO)


def list_cards(session: Session, on: dt.date) -> list[CardView]:
    """Every credit card account with its perks and their current periods."""
    cards = session.execute(
        select(Account)
        .where(Account.subtype == AccountSubtype.CREDIT_CARD)
        .order_by(Account.name, Account.id)
    ).scalars()

    result: list[CardView] = []
    for account in cards:
        rows = session.execute(
            select(CardPerk)
            .where(CardPerk.account_id == account.id)
            .order_by(CardPerk.is_active.desc(), CardPerk.name, CardPerk.id)
        ).scalars()
        views = [perk_view(session, perk, on) for perk in rows]
        result.append(
            CardView(
                account=account,
                perks=views,
                unused=sum((v.perk.value for v in views if v.is_unused_now), ZERO),
                active_perk_count=sum(1 for v in views if v.perk.is_active),
                realised_this_year=realised_this_year(session, account.id, on),
            )
        )
    return result


def history(
    session: Session,
    *,
    perk_id: int | None,
    account_id: int | None = None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    today: dt.date,
) -> History:
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

    entries: list[RedemptionEntry] = []
    realised = ZERO
    for redemption, perk, account in rows:
        period = perk_service.period_containing(
            perk.cadence, perk.anchor_on, redemption.period_start
        )
        value = realised_value(redemption, perk)
        realised += value
        entries.append(
            RedemptionEntry(
                redemption=redemption,
                perk=perk,
                account=account,
                period_end=period.end,
                realised=value,
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
        # Still from the anchor, not from the beginning of time. A period before the credit
        # was set up can now be *recorded* (ticket 076), but calling it missed would invent
        # an obligation out of a date someone typed into a form.
        cursor = max(perk.anchor_on, from_date) if from_date else perk.anchor_on
        horizon = min(to_date, today) if to_date else today
        while cursor <= horizon:
            period = perk_service.period_containing(perk.cadence, perk.anchor_on, cursor)
            # Only periods that have actually ended can be called missed. The current one
            # is still spendable.
            if period.end <= today and period.start not in recorded:
                missed += 1
            cursor = period.end

    return History(
        from_date=from_date,
        to_date=to_date,
        realised=realised,
        missed_periods=missed,
        entries=entries,
    )


def upcoming(session: Session, within_days: int, on: dt.date) -> Upcoming:
    """Unused perks whose current period ends within `within_days`, soonest first.

    The point of the feature. Closed cards are excluded — a perk on a card you no longer
    hold is not something you can still use.
    """
    rows = session.execute(
        select(CardPerk, Account)
        .join(Account, Account.id == CardPerk.account_id)
        .where(
            CardPerk.is_active.is_(True),
            Account.subtype == AccountSubtype.CREDIT_CARD,
            Account.closed_at.is_(None),
        )
    ).all()

    found: list[tuple[int, UpcomingItem]] = []
    for perk, account in rows:
        view = perk_view(session, perk, on)
        current = view.current
        if current is None or current.is_used or current.days_remaining > within_days:
            continue
        found.append((current.days_remaining, UpcomingItem(view=view, account=account)))

    # Soonest first, then by value: two perks expiring the same day are better read with
    # the expensive one at the top.
    found.sort(key=lambda pair: (pair[0], -pair[1].view.perk.value, pair[1].view.perk.name))
    items = [item for _, item in found]

    return Upcoming(
        within_days=within_days,
        as_of=on,
        total=sum((item.view.perk.value for item in items), ZERO),
        urgent=sum(
            (
                item.view.perk.value
                for item in items
                if item.view.current is not None and item.view.current.is_urgent
            ),
            ZERO,
        ),
        items=items,
    )
