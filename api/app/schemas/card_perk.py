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
    #: Amount actually used, when a partial redemption was recorded. `None` with
    #: `is_used` true means the full face value.
    used_amount_cents: Cents | None = None
    #: Whether `days_remaining` is short enough to matter *for this cadence* — 7 days on
    #: a monthly credit, 30 on an annual one. Computed by `services/perks.is_urgent` and
    #: never recomputed in the browser, so the two cannot disagree.
    is_urgent: bool = False


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
    #: Which period to mark, named by any date inside it. Defaults to today. Any past
    #: date backfills that period.
    on: dt.date | None = None
    #: How much was used. Omit for the full face value, which is what one tap means.
    amount_cents: Cents | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


class CardRead(Schema):
    """A credit card account and its perks."""

    account_id: int
    name: str
    institution: str | None = None
    is_closed: bool
    perks: list[PerkRead]
    #: Value still available in the current period, across this card's active perks.
    #: Named `unused_cents` on the wire for continuity; the UI says "available".
    unused_cents: Cents
    #: Active perks on this card. Retired ones are still in `perks`, flagged.
    active_perk_count: int
    #: The annual fee, when one is recorded. Absent is not zero.
    annual_fee_cents: Cents | None = None
    fee_renews_on: dt.date | None = None
    #: Value realised in the current fee year — redemption amounts, falling back to face
    #: value. `None` when no fee is recorded, because the figure has nothing to be
    #: measured against.
    realised_this_fee_year_cents: Cents | None = None
    fee_year_start: dt.date | None = None


class RedemptionRead(Schema):
    """One recorded redemption, for the history view."""

    perk_id: int
    perk_name: str
    account_id: int
    card_name: str
    period_start: dt.date
    period_end: dt.date
    cadence: PerkCadence
    #: What the redemption is worth: the recorded amount, or the perk's face value when
    #: no amount was recorded.
    realised_cents: Cents
    #: True when `realised_cents` came from the perk's value rather than a recorded
    #: amount, so the UI can distinguish "used it all" from "used exactly this much".
    is_face_value: bool
    note: str | None = None
    recorded_at: dt.datetime


class HistoryRead(Schema):
    """Everything recorded, oldest boundary to newest.

    No default cut-off: "show me everything" is the request this answers. `from_date` and
    `to_date` report the window actually applied, which is the full span when none was
    asked for.
    """

    from_date: dt.date | None = None
    to_date: dt.date | None = None
    realised_cents: Cents
    #: Periods that ended inside the window with nothing recorded against them. The
    #: number that changes behaviour.
    missed_periods: int
    redemptions: list[RedemptionRead]


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
    #: Of that total, the part whose period is urgent for its own cadence.
    urgent_cents: Cents
    perks: list[UpcomingPerk]
