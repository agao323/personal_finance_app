"""When a card perk's period starts and ends.

**The one place that decides what period a date is in.** Routes and screens ask this
module rather than working it out from a cadence themselves, for the same reason
rounding happens only in `services/ownership.py`: two implementations of the same
arithmetic disagree eventually, and the disagreement shows up as a perk you were told
you still had.

Nothing here reads the clock. Every function takes the date to evaluate, because the
cases worth testing are all about a specific day — the one a period rolls over on, the
29th of February, the 31st in a month with 30 days — and a function that called
`date.today()` could not be asked about any of them.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from app.models.enums import PerkCadence

#: How many months each cadence spans.
MONTHS: dict[PerkCadence, int] = {
    PerkCadence.MONTHLY: 1,
    PerkCadence.QUARTERLY: 3,
    PerkCadence.SEMIANNUAL: 6,
    PerkCadence.ANNUAL: 12,
}


@dataclass(frozen=True)
class Period:
    """A half-open window, `start <= day < end`.

    Half-open for the same reason ownership stakes are: with an inclusive end, a date
    landing exactly on a boundary belongs to two periods and which one you get depends
    on the order of your comparisons.
    """

    start: dt.date
    end: dt.date
    #: How many periods since the anchor. 0 is the first.
    index: int

    def days_remaining(self, on: dt.date) -> int:
        """Whole days from `on` until this period ends. 0 on the last day."""
        return (self.end - on).days - 1


def add_months(day: dt.date, months: int) -> dt.date:
    """`day` shifted by `months`, clamped to the end of the target month.

    A perk anchored on the 31st has no 31st in February. Clamping is the only sane
    answer, and it is why every other function here steps from the **anchor** rather
    than from the previous period: 31 Jan stepped repeatedly from the anchor gives
    28 Feb then 31 Mar, while stepping from each previous result gives 28 Feb then
    28 Mar and stays wrong for ever after one short month.
    """
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def period_containing(cadence: PerkCadence, anchor_on: dt.date, on: dt.date) -> Period | None:
    """The period `on` falls in, or None if `on` is before the perk's first period.

    None rather than a negative index: a date before the anchor is not "period -1", it
    is a question about a perk that did not exist yet, and returning a window for it
    would let a redemption be recorded against a period that never happened.
    """
    if on < anchor_on:
        return None

    step = MONTHS[cadence]
    # An estimate from plain month arithmetic, then corrected. The estimate can be off
    # by one in either direction because of day-of-month clamping, and correcting is
    # both cheaper and easier to be sure of than a closed form that handles it.
    months_between = (on.year - anchor_on.year) * 12 + (on.month - anchor_on.month)
    index = months_between // step

    while index > 0 and add_months(anchor_on, index * step) > on:
        index -= 1
    while add_months(anchor_on, (index + 1) * step) <= on:
        index += 1

    return Period(
        start=add_months(anchor_on, index * step),
        end=add_months(anchor_on, (index + 1) * step),
        index=index,
    )
