"""Credit card perks and the periods they have been used in.

**None of this is net worth.** An unused $200 airline credit is not money you have, and
nothing here may be summed into a balance — `services/net_worth.py` does not know these
tables exist and must not learn. Stated here because "total value of unused perks" is a
figure this feature reports, and a later reader could reasonably mistake it for an asset.

Perks hang off `accounts` rather than a `credit_cards` table of their own. The subtype
already exists, and a second list of the same cards would disagree with the first the
moment one was renamed or closed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.account import MONEY, Account
from app.models.enums import PerkCadence, pg_enum


class CardPerk(Base):
    """A recurring benefit on a card — a credit, a fee waiver, a free night.

    `anchor_on` is the date this perk's **first period began**, and it is the whole of
    how the two reset clocks are represented. A calendar-year credit is anchored on
    1 January; one that resets on the cardmember year is anchored on the day the card
    was opened. Periods are the anchor stepped by `cadence`, so both are the same
    arithmetic and neither needs an `opened_at` column on `accounts`.
    """

    __tablename__ = "card_perks"
    __table_args__ = (Index("ix_card_perks_account_active", "account_id", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    #: What it is worth per period. Decimal, never float — see the CI guard.
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    cadence: Mapped[PerkCadence] = mapped_column(
        pg_enum(PerkCadence, "perk_cadence"), nullable=False
    )
    anchor_on: Mapped[dt.date] = mapped_column(Date, nullable=False)

    #: Retired rather than deleted. A perk the card stopped offering still has a
    #: redemption history, and deleting it would rewrite what you did last year.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped[Account] = relationship()
    redemptions: Mapped[list[PerkRedemption]] = relationship(
        back_populates="perk", cascade="all, delete-orphan"
    )


class PerkRedemption(Base):
    """One period of one perk, marked used.

    Presence is the whole state: a row means that period was used, no row means it was
    not. There is no `is_used` column to fall out of step with whether the row exists.

    `period_start` is **stored, not derived**. It is the fact being recorded — this
    period was used — and recomputing it later from a cadence that had since been
    edited would silently move history. Effective-dated ownership stakes exist for the
    same reason.
    """

    __tablename__ = "perk_redemptions"
    __table_args__ = (
        UniqueConstraint("perk_id", "period_start", name="uq_perk_redemptions_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    perk_id: Mapped[int] = mapped_column(
        ForeignKey("card_perks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    perk: Mapped[CardPerk] = relationship(back_populates="redemptions")
