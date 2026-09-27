"""The card-perk period engine.

Every expected value here is computed by hand. A test that derives its expectation from
the same function it is testing agrees with the bug.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import PerkCadence
from app.services.perks import (
    URGENT_WITHIN,
    add_months,
    is_calendar_aligned,
    is_urgent,
    period_at,
    period_containing,
    recent_periods,
)

D = dt.date


# ── the four cadences ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cadence", "on", "start", "end"),
    [
        # A calendar-year credit: anchored 1 January.
        (PerkCadence.ANNUAL, D(2026, 6, 15), D(2026, 1, 1), D(2027, 1, 1)),
        (PerkCadence.SEMIANNUAL, D(2026, 6, 15), D(2026, 1, 1), D(2026, 7, 1)),
        (PerkCadence.SEMIANNUAL, D(2026, 7, 1), D(2026, 7, 1), D(2027, 1, 1)),
        (PerkCadence.QUARTERLY, D(2026, 6, 15), D(2026, 4, 1), D(2026, 7, 1)),
        (PerkCadence.QUARTERLY, D(2026, 12, 31), D(2026, 10, 1), D(2027, 1, 1)),
        (PerkCadence.MONTHLY, D(2026, 6, 15), D(2026, 6, 1), D(2026, 7, 1)),
        (PerkCadence.MONTHLY, D(2027, 3, 2), D(2027, 3, 1), D(2027, 4, 1)),
    ],
)
def test_calendar_anchored_periods(
    cadence: PerkCadence, on: dt.date, start: dt.date, end: dt.date
) -> None:
    period = period_containing(cadence, D(2026, 1, 1), on)

    assert (period.start, period.end) == (start, end)


def test_a_cardmember_year_is_the_same_arithmetic() -> None:
    """The whole reason there is no calendar-versus-anniversary enum.

    A card opened 14 July 2023 with an annual credit: on 1 January 2026 you are still
    in the period that began 14 July 2025. A calendar-year reading would say you had a
    fresh credit, which is the expensive kind of wrong.
    """
    period = period_containing(PerkCadence.ANNUAL, D(2023, 7, 14), D(2026, 1, 1))

    assert period is not None
    assert (period.start, period.end) == (D(2025, 7, 14), D(2026, 7, 14))
    assert period.index == 2


# ── boundaries ────────────────────────────────────────────────────────────────


def test_a_date_on_the_boundary_belongs_to_the_later_period() -> None:
    """Half-open, so `start` is in the period and `end` is not."""
    period = period_containing(PerkCadence.ANNUAL, D(2026, 1, 1), D(2027, 1, 1))

    assert period.start == D(2027, 1, 1)


def test_a_date_before_the_anchor_is_period_minus_one() -> None:
    """Ticket 076 reversed this. It used to be None.

    The anchor says where a boundary falls, not when the credit came into existence, and
    people enter the day they set the credit up in the app. Treating that as the beginning
    of history made the grid refuse to record uses there was no reason to doubt.
    """
    period = period_containing(PerkCadence.ANNUAL, D(2026, 1, 1), D(2025, 12, 31))

    assert (period.start, period.end, period.index) == (D(2025, 1, 1), D(2026, 1, 1), -1)


def test_the_anchor_day_itself_is_the_first_period() -> None:
    period = period_containing(PerkCadence.MONTHLY, D(2026, 3, 10), D(2026, 3, 10))

    assert (period.start, period.index) == (D(2026, 3, 10), 0)


# ── month-end and leap years ──────────────────────────────────────────────────


def test_a_month_end_anchor_clamps_and_then_recovers() -> None:
    """The drift bug this arithmetic exists to avoid.

    A monthly perk anchored 31 January has no 31st in February. Clamping to 28 is the
    only answer — but stepping from *each previous period* would then give 28 March and
    stay wrong for ever after one short month. Stepping from the anchor recovers.
    """
    anchor = D(2026, 1, 31)

    assert add_months(anchor, 1) == D(2026, 2, 28)
    assert add_months(anchor, 2) == D(2026, 3, 31)  # recovered, not 28 March
    assert add_months(anchor, 3) == D(2026, 4, 30)
    assert add_months(anchor, 4) == D(2026, 5, 31)


def test_the_period_containing_a_clamped_month_end() -> None:
    anchor = D(2026, 1, 31)

    period = period_containing(PerkCadence.MONTHLY, anchor, D(2026, 3, 1))

    assert period is not None
    # 28 Feb through 30 March: the February period runs until the March anchor day.
    assert (period.start, period.end) == (D(2026, 2, 28), D(2026, 3, 31))


def test_a_leap_day_anchor_survives_common_years() -> None:
    """29 February 2024, annually. Three of the next four years have no 29th."""
    anchor = D(2024, 2, 29)

    assert add_months(anchor, 12) == D(2025, 2, 28)
    assert add_months(anchor, 24) == D(2026, 2, 28)
    assert add_months(anchor, 36) == D(2027, 2, 28)
    assert add_months(anchor, 48) == D(2028, 2, 29)  # leap again


def test_a_perk_anchored_on_a_leap_day_reports_the_right_period() -> None:
    period = period_containing(PerkCadence.ANNUAL, D(2024, 2, 29), D(2026, 2, 28))

    assert period is not None
    assert (period.start, period.end) == (D(2026, 2, 28), D(2027, 2, 28))


# ── days remaining ────────────────────────────────────────────────────────────


def test_days_remaining_is_zero_on_the_last_day() -> None:
    """Off-by-one here is the difference between "expires today" and "already gone"."""
    period = period_containing(PerkCadence.MONTHLY, D(2026, 1, 1), D(2026, 1, 31))

    assert period is not None
    assert period.end == D(2026, 2, 1)
    assert period.days_remaining(D(2026, 1, 31)) == 0
    assert period.days_remaining(D(2026, 1, 30)) == 1
    assert period.days_remaining(D(2026, 1, 1)) == 30


# ── the database constraint ───────────────────────────────────────────────────


def test_a_period_can_only_be_redeemed_once(db_session: Session, make_account: object) -> None:
    """Presence is the state, so the same period twice must be refused.

    Without this the button being double-tapped would record two redemptions and any
    count of what you used this year would quietly overstate.
    """
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")  # type: ignore[operator]
    perk_id = db_session.execute(
        text(
            "INSERT INTO card_perks (account_id, name, value, cadence, anchor_on) "
            "VALUES (:a, 'Airline credit', 200.00, 'annual', '2026-01-01') RETURNING id"
        ),
        {"a": account_id},
    ).scalar_one()

    db_session.execute(
        text("INSERT INTO perk_redemptions (perk_id, period_start) VALUES (:p, '2026-01-01')"),
        {"p": perk_id},
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO perk_redemptions (perk_id, period_start) VALUES (:p, '2026-01-01')"),
            {"p": perk_id},
        )
        db_session.flush()


def test_a_perk_must_be_worth_something(db_session: Session, make_account: object) -> None:
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")  # type: ignore[operator]

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO card_perks (account_id, name, value, cadence, anchor_on) "
                "VALUES (:a, 'Nothing', 0, 'annual', '2026-01-01')"
            ),
            {"a": account_id},
        )
        db_session.flush()


# ── urgency, which varies by cadence (053) ────────────────────────────────────


@pytest.mark.parametrize(
    ("cadence", "threshold"),
    [
        (PerkCadence.MONTHLY, 7),
        (PerkCadence.QUARTERLY, 14),
        (PerkCadence.SEMIANNUAL, 21),
        (PerkCadence.ANNUAL, 30),
    ],
)
def test_urgency_turns_on_at_each_cadences_own_threshold(
    cadence: PerkCadence, threshold: int
) -> None:
    """The whole point of varying it.

    A single global number was what made the old page unhelpful: 30 days is urgent for
    most of a monthly credit's life, and is barely time to book a flight on an annual one.
    """
    assert is_urgent(cadence, threshold) is True
    assert is_urgent(cadence, threshold - 1) is True
    assert is_urgent(cadence, threshold + 1) is False


def test_the_last_day_is_urgent_at_every_cadence() -> None:
    """`days_remaining` is 0 on the final day, so nothing may read it as safe."""
    for cadence in PerkCadence:
        assert is_urgent(cadence, 0) is True


def test_a_monthly_credit_is_not_urgent_for_most_of_its_life() -> None:
    """The failure the old fixed 45-day window produced, asserted directly."""
    assert is_urgent(PerkCadence.MONTHLY, 20) is False
    assert is_urgent(PerkCadence.ANNUAL, 20) is True


def test_every_cadence_has_a_threshold() -> None:
    """A cadence added later without one would raise KeyError on a live request."""
    assert set(URGENT_WITHIN) == set(PerkCadence)


# ── partial redemption amounts (053) ──────────────────────────────────────────


@pytest.mark.parametrize("bad", ["0", "-1.00"])
def test_a_redemption_amount_must_be_positive(
    db_session: Session, make_account: Callable[..., int], bad: str
) -> None:
    """Zero is not a partial redemption — it is an unused period, and no row says that."""
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")
    perk_id = db_session.execute(
        text(
            "INSERT INTO card_perks (account_id, name, value, cadence, anchor_on) "
            "VALUES (:a, 'Travel', 200.00, 'annual', '2026-01-01') RETURNING id"
        ),
        {"a": account_id},
    ).scalar_one()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO perk_redemptions (perk_id, period_start, amount) "
                "VALUES (:p, '2026-01-01', :amt)"
            ),
            {"p": perk_id, "amt": Decimal(bad)},
        )
        db_session.flush()


def test_a_null_amount_is_allowed_and_means_full_value(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """What a one-tap mark records. Null rather than copying the perk's value in, which
    would leave history disagreeing with a perk whose value later changed."""
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")
    perk_id = db_session.execute(
        text(
            "INSERT INTO card_perks (account_id, name, value, cadence, anchor_on) "
            "VALUES (:a, 'Travel', 200.00, 'annual', '2026-01-01') RETURNING id"
        ),
        {"a": account_id},
    ).scalar_one()

    db_session.execute(
        text("INSERT INTO perk_redemptions (perk_id, period_start) VALUES (:p, '2026-01-01')"),
        {"p": perk_id},
    )
    db_session.flush()

    stored = db_session.execute(
        text("SELECT amount FROM perk_redemptions WHERE perk_id = :p"), {"p": perk_id}
    ).scalar_one()
    assert stored is None


def test_an_annual_fee_may_be_absent_but_not_negative(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Absent is not zero: a card with no fee recorded must not claim its fee is $0."""
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")

    stored = db_session.execute(
        text("SELECT annual_fee FROM accounts WHERE id = :i"), {"i": account_id}
    ).scalar_one()
    assert stored is None

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE accounts SET annual_fee = -1 WHERE id = :i"), {"i": account_id}
        )
        db_session.flush()


# ── indexing periods, and listing recent ones ─────────────────────────────────


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4, 5])
def test_period_at_and_period_containing_are_inverses(index: int) -> None:
    """The property the grid depends on, across the month that breaks naive arithmetic.

    Anchored on the 31st: February has no 31st, so period 0 ends on the 28th and period 1
    begins there. A chip built from an index must resolve back to the same index, or
    clicking it would mark a different period than the one it is labelled with.
    """
    anchor = D(2026, 1, 31)

    period = period_at(PerkCadence.MONTHLY, anchor, index)
    resolved = period_containing(PerkCadence.MONTHLY, anchor, period.start)

    assert period.start < period.end
    assert resolved is not None
    assert resolved.index == index
    assert (resolved.start, resolved.end) == (period.start, period.end)


@pytest.mark.parametrize("index", [-1, -2, -8, -13])
def test_period_at_and_period_containing_are_inverses_before_the_anchor(index: int) -> None:
    """The same round-trip property, on the side of the anchor that used to be refused.

    `add_months` handles a negative span because Python floors both division and modulo
    toward negative infinity — month -3 lands in October of the previous year. Asserted
    rather than assumed.
    """
    anchor = D(2026, 8, 13)

    period = period_at(PerkCadence.MONTHLY, anchor, index)
    resolved = period_containing(PerkCadence.MONTHLY, anchor, period.start)

    assert period.start < period.end
    assert resolved.index == index
    assert (resolved.start, resolved.end) == (period.start, period.end)


def test_negative_periods_cross_the_year_boundary_correctly() -> None:
    """The case the floor-division reasoning is actually about."""
    # Eight months before 13 August 2026 is 13 December 2025, not 13 December 2026.
    period = period_at(PerkCadence.MONTHLY, D(2026, 8, 13), -8)

    assert (period.start, period.end) == (D(2025, 12, 13), D(2026, 1, 13))


def test_recent_periods_ends_with_the_one_containing_the_date() -> None:
    periods = recent_periods(PerkCadence.MONTHLY, D(2026, 1, 1), D(2026, 6, 15), 3)

    # Oldest first, newest last: reading order for a row of months.
    assert [p.start for p in periods] == [D(2026, 4, 1), D(2026, 5, 1), D(2026, 6, 1)]
    assert periods[-1].start <= D(2026, 6, 15) < periods[-1].end


def test_recent_periods_on_the_anchor_itself_still_offers_a_full_year() -> None:
    """Twelve chips, ending at the anchor's own period."""
    periods = recent_periods(PerkCadence.MONTHLY, D(2026, 1, 31), D(2026, 1, 31), 12)

    assert len(periods) == 12
    assert periods[-1].index == 0
    assert periods[-1].start == D(2026, 1, 31)
    assert periods[0].start == D(2025, 2, 28)


def test_recent_periods_does_not_clip_at_the_anchor() -> None:
    """The bug ticket 076 fixes, as a test.

    A monthly credit anchored 13 August offered exactly two chips — August and September —
    and no way at all to record the eight months before it.
    """
    periods = recent_periods(PerkCadence.MONTHLY, D(2026, 8, 13), D(2026, 9, 27), 12)

    assert len(periods) == 12
    assert [periods[0].start, periods[-1].start] == [D(2025, 10, 13), D(2026, 9, 13)]


def test_recent_periods_covers_the_whole_calendar_year_at_every_cadence() -> None:
    """`PERIODS_BACK` in the browser promises the current year. This is what makes it true.

    Checked on the last day of the year, when the year holds the most periods it ever will.
    """
    depth = {
        PerkCadence.MONTHLY: 12,
        PerkCadence.QUARTERLY: 8,
        PerkCadence.SEMIANNUAL: 4,
        PerkCadence.ANNUAL: 3,
    }
    for cadence, count in depth.items():
        periods = recent_periods(cadence, D(2026, 1, 1), D(2026, 12, 31), count)
        assert periods[0].start <= D(2026, 1, 1), cadence


def test_recent_periods_counts_periods_not_days() -> None:
    """Three annual periods span three years; three monthly ones span three months."""
    annual = recent_periods(PerkCadence.ANNUAL, D(2020, 1, 1), D(2026, 6, 15), 3)

    assert [p.start for p in annual] == [D(2024, 1, 1), D(2025, 1, 1), D(2026, 1, 1)]
    assert [p.index for p in annual] == [4, 5, 6]


def test_recent_periods_of_none_is_empty() -> None:
    assert recent_periods(PerkCadence.ANNUAL, D(2026, 1, 1), D(2026, 6, 1), 0) == []


def test_recent_periods_ends_at_the_date_asked_about_not_at_the_anchor() -> None:
    """A future anchor still reports the period containing today, not the anchor's."""
    periods = recent_periods(PerkCadence.MONTHLY, D(2027, 5, 1), D(2026, 9, 27), 3)

    assert periods[-1].start <= D(2026, 9, 27) < periods[-1].end


# ── calendar alignment ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cadence", "aligned_months"),
    [
        (PerkCadence.MONTHLY, list(range(1, 13))),
        (PerkCadence.QUARTERLY, [1, 4, 7, 10]),
        (PerkCadence.SEMIANNUAL, [1, 7]),
        (PerkCadence.ANNUAL, [1]),
    ],
)
def test_which_anchors_put_a_cadence_on_calendar_boundaries(
    cadence: PerkCadence, aligned_months: list[int]
) -> None:
    """Calendar quarters are January, April, July and October. Hand-listed, not derived."""
    found = [month for month in range(1, 13) if is_calendar_aligned(cadence, D(2026, month, 1))]

    assert found == aligned_months


@pytest.mark.parametrize("cadence", list(PerkCadence))
def test_a_day_other_than_the_first_is_never_calendar_aligned(cadence: PerkCadence) -> None:
    assert not is_calendar_aligned(cadence, D(2026, 1, 15))


def test_the_first_of_january_aligns_every_cadence() -> None:
    """Which is what makes it usable as the one default."""
    assert all(is_calendar_aligned(cadence, D(2026, 1, 1)) for cadence in PerkCadence)


def test_a_september_anchored_quarterly_credit_resets_in_december() -> None:
    """The reported behaviour, and it is correct arithmetic — just not what was meant.

    Kept as a test so nobody "fixes" the engine when the defect was the default.
    """
    period = period_containing(PerkCadence.QUARTERLY, D(2026, 9, 1), D(2026, 9, 27))

    assert (period.start, period.end) == (D(2026, 9, 1), D(2026, 12, 1))
    assert not is_calendar_aligned(PerkCadence.QUARTERLY, D(2026, 9, 1))
