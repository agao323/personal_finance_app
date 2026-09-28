"""Calendar periods: the one place "this quarter" and "last year" are turned into dates.

Every analysis and every tool that takes a period resolves it here, relative to a `today`
it is given — nothing reads the clock, for the reason `services/perks.py` gives.

**Presets are calendar-aligned.** "Last quarter" is 1 April to 30 June, not the 92 days
before today. `services/spend.prior_period` compares against an equal-length window, which
is right for the dashboard's "vs the previous period" and wrong for "this quarter vs last":
a 92-day window before 1 July starts on 31 March.

**A partial period is compared like-for-like.** On 20 August, "this quarter" is 1 July to
20 August — 51 days — and comparing it with all of last quarter shows a spending drop that
is really a calendar. `like_for_like` cuts the other window to the same number of days.
Runway never averages in the current month for the same reason.
"""

from __future__ import annotations

import calendar
import datetime as dt
import enum
from dataclasses import dataclass


class PeriodPreset(enum.StrEnum):
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    YEAR_TO_DATE = "year_to_date"
    LAST_YEAR = "last_year"
    TRAILING_3_MONTHS = "trailing_3_months"
    TRAILING_12_MONTHS = "trailing_12_months"
    CUSTOM = "custom"


#: The longest window any period may span, unless a caller asks for less.
MAX_DAYS = 366


class PeriodError(ValueError):
    """A period that cannot be resolved. The message says what to change."""


@dataclass(frozen=True)
class Window:
    """An inclusive date range, and whether it is a period still in progress."""

    start: dt.date
    end: dt.date
    #: The last day of the full period. Equal to `end` unless the period is partial.
    full_end: dt.date
    label: str

    @property
    def is_partial(self) -> bool:
        return self.end < self.full_end

    @property
    def days(self) -> int:
        """Days covered, counting both ends."""
        return (self.end - self.start).days + 1


def _month_end(year: int, month: int) -> dt.date:
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def _quarter_start(day: dt.date) -> dt.date:
    return dt.date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _quarter_label(start: dt.date) -> str:
    return f"Q{(start.month - 1) // 3 + 1} {start.year}"


def _trailing(today: dt.date, months: int) -> Window:
    """The `months` complete months before the one `today` is in."""
    end_year, end_month = _shift_month(today.year, today.month, -1)
    start_year, start_month = _shift_month(today.year, today.month, -months)
    end = _month_end(end_year, end_month)
    return Window(
        start=dt.date(start_year, start_month, 1),
        end=end,
        full_end=end,
        label=f"the {months} complete months to {end:%B %Y}",
    )


def resolve(
    preset: PeriodPreset,
    today: dt.date,
    start: dt.date | None = None,
    end: dt.date | None = None,
    max_days: int = MAX_DAYS,
) -> Window:
    """Turn a preset — or `custom` with explicit dates — into a window ending by `today`."""
    if preset is not PeriodPreset.CUSTOM and (start is not None or end is not None):
        raise PeriodError("Give start and end only with the custom preset.")

    if preset is PeriodPreset.THIS_MONTH:
        full_end = _month_end(today.year, today.month)
        window = Window(today.replace(day=1), today, full_end, f"{today:%B %Y} to date")
    elif preset is PeriodPreset.LAST_MONTH:
        year, month = _shift_month(today.year, today.month, -1)
        end_ = _month_end(year, month)
        window = Window(dt.date(year, month, 1), end_, end_, f"{end_:%B %Y}")
    elif preset is PeriodPreset.THIS_QUARTER:
        q_start = _quarter_start(today)
        year, month = _shift_month(q_start.year, q_start.month, 2)
        window = Window(
            q_start, today, _month_end(year, month), f"{_quarter_label(q_start)} to date"
        )
    elif preset is PeriodPreset.LAST_QUARTER:
        this_start = _quarter_start(today)
        end_ = this_start - dt.timedelta(days=1)
        q_start = _quarter_start(end_)
        window = Window(q_start, end_, end_, _quarter_label(q_start))
    elif preset is PeriodPreset.YEAR_TO_DATE:
        window = Window(
            dt.date(today.year, 1, 1), today, dt.date(today.year, 12, 31), f"{today.year} to date"
        )
    elif preset is PeriodPreset.LAST_YEAR:
        year_ = today.year - 1
        window = Window(
            dt.date(year_, 1, 1), dt.date(year_, 12, 31), dt.date(year_, 12, 31), str(year_)
        )
    elif preset is PeriodPreset.TRAILING_3_MONTHS:
        window = _trailing(today, 3)
    elif preset is PeriodPreset.TRAILING_12_MONTHS:
        window = _trailing(today, 12)
    else:
        if start is None or end is None:
            raise PeriodError("The custom preset needs both start and end.")
        if start > end:
            raise PeriodError("start must be on or before end.")
        if end > today:
            raise PeriodError(f"end cannot be after today ({today.isoformat()}).")
        window = Window(start, end, end, f"{start.isoformat()} to {end.isoformat()}")

    if window.days > max_days:
        raise PeriodError(
            f"A period can span at most {max_days} days; this one spans {window.days}."
        )
    return window


def like_for_like(current: Window, other: Window) -> Window:
    """`other` cut to the same number of days as `current`, when `current` is partial.

    Equal day counts rather than equal day-of-month: 1 July to 20 August is 51 days, so the
    matching slice of last quarter is 1 April to 21 May. A comparison of unequal spans is
    the thing this exists to prevent.
    """
    if not current.is_partial:
        return other
    end = min(other.start + dt.timedelta(days=current.days - 1), other.end)
    return Window(other.start, end, other.full_end, f"{other.label}, first {current.days} days")
