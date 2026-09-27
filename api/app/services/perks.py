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


#: When a credit's period is short enough that it should start shouting.
#:
#: **Fixed per cadence, and deliberately not configurable.** A single global threshold is
#: the thing that made the old page unhelpful: 30 days is noise on a monthly credit — it is
#: urgent for most of its life — and far too late on an annual one, where a month is barely
#: time to book the flight the credit pays for. Roughly "the last quarter of a month, the
#: last fortnight of a quarter".
#:
#: One table anyone can read beats a setting nobody revisits.
URGENT_WITHIN: dict[PerkCadence, int] = {
    PerkCadence.MONTHLY: 7,
    PerkCadence.QUARTERLY: 14,
    PerkCadence.SEMIANNUAL: 21,
    PerkCadence.ANNUAL: 30,
}


def is_calendar_aligned(cadence: PerkCadence, anchor_on: dt.date) -> bool:
    """Whether this anchor puts the periods on calendar boundaries.

    Calendar quarters are January, April, July and October; calendar halves are January and
    July; a calendar year is January. All of them start on the 1st. One rule covers every
    cadence: the anchor is the 1st of a month, and that month is a whole number of steps from
    January.

    Here rather than in the browser because it is a statement about what the period
    arithmetic will do, and the form that sets the anchor is the last place that should hold
    a second opinion about it.
    """
    return anchor_on.day == 1 and (anchor_on.month - 1) % MONTHS[cadence] == 0


def calendar_anchor(on: dt.date) -> dt.date:
    """The anchor that puts any cadence on calendar boundaries.

    1 January serves all four: months from the 1st, quarters at Jan/Apr/Jul/Oct, halves at
    Jan/Jul, and the calendar year itself.
    """
    return dt.date(on.year, 1, 1)


def is_urgent(cadence: PerkCadence, days_remaining: int) -> bool:
    """Whether this many days left is urgent for this cadence.

    Computed here and only here. The browser reads the answer off the API rather than
    recomputing it — a second implementation would drift, and the symptom would be a page
    calling a credit safe while the API called it urgent.

    `days_remaining` is 0 on the final day of a period (see `Period.days_remaining`), so
    a perk on its last day is urgent at every cadence.
    """
    return days_remaining <= URGENT_WITHIN[cadence]


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


def period_at(cadence: PerkCadence, anchor_on: dt.date, index: int) -> Period:
    """The `index`-th period relative to the anchor. 0 is the one the anchor begins.

    **Negative indices are periods before the anchor, and they are legitimate** (ticket 076).
    `anchor_on` says where a boundary falls, not when the credit came into existence: it is
    what makes a monthly credit reset on the 13th rather than the 1st. People routinely enter
    the day they set the credit up in this app, and treating that as the beginning of history
    made the grid refuse to record uses it had no reason to doubt.

    The inverse of `period_containing`, and the two must agree: a period built from an
    index must contain its own start, and `period_containing` asked about that start must
    return the same index. Both step from the anchor for the reason `add_months` explains.
    """
    step = MONTHS[cadence]
    return Period(
        start=add_months(anchor_on, index * step),
        end=add_months(anchor_on, (index + 1) * step),
        index=index,
    )


def recent_periods(
    cadence: PerkCadence, anchor_on: dt.date, on: dt.date, count: int
) -> list[Period]:
    """The `count` periods ending with the one containing `on`, oldest first.

    Oldest first because that is reading order for a row of months, and the newest being
    last puts the current period nearest the controls that act on it.

    Always `count` periods, including ones before the anchor. It used to stop at the anchor,
    which meant a monthly credit set up in August offered two chips and no way to record the
    eight months before it — see `period_at` for why the anchor is not a start date.
    """
    if count <= 0:
        return []
    current = period_containing(cadence, anchor_on, on)
    first = current.index - count + 1
    return [period_at(cadence, anchor_on, index) for index in range(first, current.index + 1)]


def period_containing(cadence: PerkCadence, anchor_on: dt.date, on: dt.date) -> Period:
    """The period `on` falls in. Always answers.

    It used to return None for a date before the anchor. That conflated two different
    questions — "has this credit started yet?" and "which window is this date in?" — and only
    the first has anything to do with the anchor. Callers that care whether a credit has
    started compare the anchor to the date themselves, which is one comparison and says what
    it means.
    """
    step = MONTHS[cadence]
    # An estimate from plain month arithmetic, then corrected. The estimate can be off
    # by one in either direction because of day-of-month clamping, and correcting is
    # both cheaper and easier to be sure of than a closed form that handles it.
    months_between = (on.year - anchor_on.year) * 12 + (on.month - anchor_on.month)
    index = months_between // step

    while add_months(anchor_on, index * step) > on:
        index -= 1
    while add_months(anchor_on, (index + 1) * step) <= on:
        index += 1

    return period_at(cadence, anchor_on, index)
