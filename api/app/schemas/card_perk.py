"""Credit card perks.

Money crosses the wire as **integer cents**, like everywhere else. A perk's value is not
a balance and is never summed into net worth — see the note in `models/card_perk.py` —
but it is money, and the rule holds for anything that gets added up.
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from app.models.enums import PerkCadence
from app.schemas.common import Cents, Schema


class PerkPeriodRead(Schema):
    """Which window a perk is currently in, and whether it has been spent."""

    start: dt.date
    #: Exclusive. The period runs up to but not including this date.
    end: dt.date
    #: Whole days left, 0 on the final day. Not `end - today`, which reads as one more
    #: day than you have.
    days_remaining: int
    is_used: bool
    used_note: str | None = None


class PerkRead(Schema):
    id: int
    account_id: int
    name: str
    description: str | None = None
    value_cents: Cents
    cadence: PerkCadence
    anchor_on: dt.date
    is_active: bool
    #: Absent when the evaluated date falls before `anchor_on` — the perk exists but
    #: has not started yet, which is different from having an unused period.
    current_period: PerkPeriodRead | None = None


class PerkCreate(Schema):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    value_cents: Cents = Field(gt=0)
    cadence: PerkCadence
    anchor_on: dt.date = Field(
        description=(
            "The date this perk's first period began. 1 January for a calendar-year "
            "credit; the day the card was opened for one that resets on the cardmember "
            "year."
        )
    )


class PerkUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    value_cents: Cents | None = Field(default=None, gt=0)
    cadence: PerkCadence | None = None
    anchor_on: dt.date | None = None
    is_active: bool | None = None


class RedemptionCreate(Schema):
    #: Which period to mark, named by any date inside it. Defaults to today.
    on: dt.date | None = None
    note: str | None = Field(default=None, max_length=500)


class CardRead(Schema):
    """A credit card account and its perks."""

    account_id: int
    name: str
    institution: str | None = None
    is_closed: bool
    perks: list[PerkRead]
    #: Unused value in the current period, across this card's active perks.
    unused_cents: Cents


class UpcomingPerk(Schema):
    """An unused perk whose period is about to end."""

    perk: PerkRead
    account_id: int
    card_name: str


class UpcomingRead(Schema):
    """What the whole feature is for: what is about to be lost.

    Sorted by how soon the period ends, because a list you have to scan to find the
    urgent thing is a worse version of the spreadsheet this replaces.
    """

    within_days: int
    as_of: dt.date
    total_cents: Cents
    perks: list[UpcomingPerk]
