"""Card value: what each card returned in a calendar year, against its fee and against what
was on offer.

"Is this card worth its fee?" is the question card tracking exists for (ticket 059).
Realised value is `services/cards`' rule — the recorded amount, or face value for a one-tap
mark, **never what was merely available**, which would flatter every card. A period belongs
to the year it began in (ticket 073), so this agrees with the Cards screen's "realised this
year" by construction, and a test holds it to that.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.card_perk import CardPerk
from app.models.enums import AccountSubtype
from app.services import cards as card_service
from app.services import perks as perk_service
from app.services.analysis.numbers import ZERO, ratio_bps


@dataclass(frozen=True)
class CardValue:
    account: Account
    year: int
    #: The fee is only what was recorded; `None` means unknown, not free.
    fee: Decimal | None
    realised: Decimal
    #: Face value of every period of an active perk that began in the year so far.
    available: Decimal
    missed_periods: int

    @property
    def utilisation_bps(self) -> int | None:
        return ratio_bps(self.realised, self.available) if self.available else None

    @property
    def net(self) -> Decimal:
        """Realised less the fee. With no fee recorded, it is the realised value."""
        return self.realised - (self.fee or ZERO)


def _available(perk: CardPerk, start: dt.date, on: dt.date) -> Decimal:
    """Face value of the perk's periods that began in `[start, on]`, from its anchor on."""
    total = ZERO
    first = perk_service.period_containing(perk.cadence, perk.anchor_on, max(start, perk.anchor_on))
    index = first.index if first.start >= start else first.index + 1
    while True:
        period = perk_service.period_at(perk.cadence, perk.anchor_on, index)
        if period.start > on:
            return total
        if period.start >= perk.anchor_on:
            total += perk.value
        index += 1


def value(session: Session, year: int, today: dt.date) -> list[CardValue]:
    """Every credit card, open or closed during the year, for the calendar year `year`."""
    start = dt.date(year, 1, 1)
    on = min(today, dt.date(year, 12, 31))
    cards = session.execute(
        select(Account)
        .where(
            Account.subtype == AccountSubtype.CREDIT_CARD,
            (Account.closed_at.is_(None)) | (Account.closed_at > start),
        )
        .order_by(Account.name, Account.id)
    ).scalars()

    result: list[CardValue] = []
    for account in cards:
        perks = session.execute(
            select(CardPerk).where(CardPerk.account_id == account.id, CardPerk.is_active.is_(True))
        ).scalars()
        history = card_service.history(
            session, perk_id=None, account_id=account.id, from_date=start, to_date=on, today=today
        )
        result.append(
            CardValue(
                account=account,
                year=year,
                fee=account.annual_fee,
                realised=card_service.realised_this_year(session, account.id, on),
                available=sum((_available(p, start, on) for p in perks), ZERO),
                missed_periods=history.missed_periods,
            )
        )
    return result
