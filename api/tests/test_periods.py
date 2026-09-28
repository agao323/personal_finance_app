"""Calendar periods, on the days that break naive date arithmetic."""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.analysis.periods import PeriodError, PeriodPreset, like_for_like, resolve

P = PeriodPreset
D = dt.date


@pytest.mark.parametrize(
    ("preset", "today", "start", "end", "full_end"),
    [
        (P.THIS_MONTH, D(2026, 2, 14), D(2026, 2, 1), D(2026, 2, 14), D(2026, 2, 28)),
        (P.THIS_MONTH, D(2028, 2, 29), D(2028, 2, 1), D(2028, 2, 29), D(2028, 2, 29)),
        (P.LAST_MONTH, D(2026, 1, 10), D(2025, 12, 1), D(2025, 12, 31), D(2025, 12, 31)),
        (P.LAST_MONTH, D(2026, 3, 31), D(2026, 2, 1), D(2026, 2, 28), D(2026, 2, 28)),
        (P.THIS_QUARTER, D(2026, 8, 20), D(2026, 7, 1), D(2026, 8, 20), D(2026, 9, 30)),
        (P.THIS_QUARTER, D(2026, 12, 31), D(2026, 10, 1), D(2026, 12, 31), D(2026, 12, 31)),
        (P.LAST_QUARTER, D(2026, 8, 20), D(2026, 4, 1), D(2026, 6, 30), D(2026, 6, 30)),
        (P.LAST_QUARTER, D(2026, 1, 1), D(2025, 10, 1), D(2025, 12, 31), D(2025, 12, 31)),
        (P.YEAR_TO_DATE, D(2026, 9, 27), D(2026, 1, 1), D(2026, 9, 27), D(2026, 12, 31)),
        (P.LAST_YEAR, D(2026, 9, 27), D(2025, 1, 1), D(2025, 12, 31), D(2025, 12, 31)),
        (P.TRAILING_3_MONTHS, D(2026, 3, 15), D(2025, 12, 1), D(2026, 2, 28), D(2026, 2, 28)),
        (P.TRAILING_12_MONTHS, D(2026, 1, 5), D(2025, 1, 1), D(2025, 12, 31), D(2025, 12, 31)),
    ],
)
def test_presets_are_calendar_aligned(
    preset: PeriodPreset, today: dt.date, start: dt.date, end: dt.date, full_end: dt.date
) -> None:
    window = resolve(preset, today)

    assert (window.start, window.end, window.full_end) == (start, end, full_end)
    assert window.is_partial == (end < full_end)


def test_custom_needs_both_dates_in_order_and_not_in_the_future() -> None:
    today = D(2026, 9, 27)
    assert resolve(P.CUSTOM, today, D(2026, 1, 1), D(2026, 1, 31)).days == 31

    with pytest.raises(PeriodError):
        resolve(P.CUSTOM, today, D(2026, 1, 1))
    with pytest.raises(PeriodError):
        resolve(P.CUSTOM, today, D(2026, 2, 1), D(2026, 1, 1))
    with pytest.raises(PeriodError):
        resolve(P.CUSTOM, today, D(2026, 9, 1), D(2026, 10, 1))
    with pytest.raises(PeriodError):
        resolve(P.LAST_MONTH, today, D(2026, 1, 1), D(2026, 1, 31))


def test_the_span_is_capped() -> None:
    with pytest.raises(PeriodError):
        resolve(P.CUSTOM, D(2026, 9, 27), D(2024, 1, 1), D(2026, 1, 1))
    assert resolve(P.CUSTOM, D(2026, 9, 27), D(2024, 1, 1), D(2026, 1, 1), max_days=800).days == 732


def test_a_partial_quarter_is_compared_on_equal_days() -> None:
    today = D(2026, 8, 20)
    current = resolve(P.THIS_QUARTER, today)
    prior = like_for_like(current, resolve(P.LAST_QUARTER, today))

    assert current.days == 51
    assert (prior.start, prior.end) == (D(2026, 4, 1), D(2026, 5, 21))
    assert prior.days == 51


def test_a_complete_period_is_compared_whole() -> None:
    today = D(2026, 8, 20)
    last = resolve(P.LAST_MONTH, today)
    before = resolve(P.CUSTOM, today, D(2026, 6, 1), D(2026, 6, 30))

    assert like_for_like(last, before) == before
