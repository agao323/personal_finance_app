"""The card-perk period engine.

Every expected value here is computed by hand. A test that derives its expectation from
the same function it is testing agrees with the bug.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import PerkCadence
from app.services.perks import add_months, period_containing

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

    assert period is not None
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

    assert period is not None
    assert period.start == D(2027, 1, 1)


def test_a_date_before_the_anchor_is_in_no_period() -> None:
    """Not "period -1" — a question about a perk that did not exist yet."""
    assert period_containing(PerkCadence.ANNUAL, D(2026, 1, 1), D(2025, 12, 31)) is None


def test_the_anchor_day_itself_is_the_first_period() -> None:
    period = period_containing(PerkCadence.MONTHLY, D(2026, 3, 10), D(2026, 3, 10))

    assert period is not None
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
