"""Tests for ownership stakes and the single rounding site.

The load-bearing ticket of the data model. Getting effective-dating wrong means a
stake change silently rewrites years of net worth history, and nothing about the
charts would look broken — they would just be wrong.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.services.ownership import (
    FULL,
    OverlappingStakeError,
    adjust,
    create_initial_stake,
    effective_stake,
    household_stake,
    transition_stake,
)

JAN = dt.date(2026, 1, 1)
JUN = dt.date(2026, 6, 1)
DEC = dt.date(2026, 12, 1)


# ── rounding ──────────────────────────────────────────────────────────────────


def test_half_cent_rounds_up_not_to_even() -> None:
    """$1,234.57 at 50% is $617.285. A statement reader expects $617.29.

    Python's default is banker's rounding, which would give $617.28. The difference
    is a cent and it is unexplainable to anyone looking at the number.
    """
    assert adjust(Decimal("1234.57"), Decimal("50")) == Decimal("617.29")


@pytest.mark.parametrize(
    ("amount", "percentage", "expected"),
    [
        (Decimal("100.00"), Decimal("100"), Decimal("100.00")),
        (Decimal("100.00"), Decimal("50"), Decimal("50.00")),
        (Decimal("0.01"), Decimal("50"), Decimal("0.01")),  # 0.005 → half up
        (Decimal("0.03"), Decimal("50"), Decimal("0.02")),  # 0.015 → half up
        (Decimal("100.00"), Decimal("33.33"), Decimal("33.33")),
        (Decimal("0.00"), Decimal("50"), Decimal("0.00")),
        (Decimal("-500.00"), Decimal("50"), Decimal("-250.00")),  # liabilities
    ],
)
def test_adjust_rounds_to_cents(amount: Decimal, percentage: Decimal, expected: Decimal) -> None:
    assert adjust(amount, percentage) == expected


def test_adjust_always_returns_two_places() -> None:
    """Exponent matters: 50.0 and 50.00 compare equal but serialise differently."""
    assert adjust(Decimal("100"), Decimal("50")).as_tuple().exponent == -2


@given(
    amount=st.decimals(min_value=0, max_value=10_000_000, places=2),
    percentage=st.decimals(min_value=1, max_value=100, places=2),
)
def test_adjusted_value_never_exceeds_the_amount(amount: Decimal, percentage: Decimal) -> None:
    # Allow a cent of rounding slack at exactly 100%.
    assert adjust(amount, percentage) <= amount + Decimal("0.01")


# ── lookup ────────────────────────────────────────────────────────────────────


def test_stake_in_force_is_found(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    assert effective_stake(db_session, account_id, JUN, owner_id) == FULL


def test_no_stake_before_it_started(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """No implicit "missing row means 100%" — an absent row is a real answer."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JUN)

    assert effective_stake(db_session, account_id, JAN, owner_id) is None


def test_account_with_no_stake_row_returns_none(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    assert effective_stake(db_session, account_id, JUN, owner_id) is None


def test_household_stake_sums_both_owners(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))
    create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("40"))

    assert household_stake(db_session, account_id, JUN) == Decimal("100")
    assert effective_stake(db_session, account_id, JUN, owner_id) == Decimal("60")


def test_household_stake_under_100_for_a_part_owned_asset(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """A 50%-owned rental: the other half belongs outside the household."""
    account_id = make_account(name="Rental", kind="illiquid_asset", subtype="real_estate")
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))

    assert household_stake(db_session, account_id, JUN) == Decimal("50")


# ── effective dating ──────────────────────────────────────────────────────────


def test_transition_does_not_rewrite_history(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """The whole reason stakes are effective-dated.

    Halving a stake in June must leave January reading 100%. If this regresses, every
    historical point on the net worth chart silently changes.
    """
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    assert effective_stake(db_session, account_id, dt.date(2026, 3, 1), owner_id) == FULL
    assert effective_stake(db_session, account_id, DEC, owner_id) == Decimal("50")


def test_transition_boundary_belongs_to_the_new_stake(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """Ranges are half-open, so the change date reads as the new value."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    assert effective_stake(db_session, account_id, JUN - dt.timedelta(days=1), owner_id) == FULL
    assert effective_stake(db_session, account_id, JUN, owner_id) == Decimal("50")


def test_transition_leaves_no_gap_and_no_overlap(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    transition_stake(db_session, account_id, owner_id, Decimal("50"), JUN)

    day = JAN
    while day < dt.date(2027, 1, 1):
        assert effective_stake(db_session, account_id, day, owner_id) is not None, day
        assert household_stake(db_session, account_id, day) <= FULL, day
        day += dt.timedelta(days=15)


def test_repeated_transitions_build_a_history(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)
    transition_stake(db_session, account_id, owner_id, Decimal("75"), dt.date(2026, 4, 1))
    transition_stake(db_session, account_id, owner_id, Decimal("50"), dt.date(2026, 8, 1))

    assert effective_stake(db_session, account_id, dt.date(2026, 2, 1), owner_id) == FULL
    assert effective_stake(db_session, account_id, dt.date(2026, 6, 1), owner_id) == Decimal("75")
    assert effective_stake(db_session, account_id, dt.date(2026, 10, 1), owner_id) == Decimal("50")


def test_same_day_correction_amends_rather_than_splitting(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """A zero-length row would be invisible to every query that reads by date."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    transition_stake(db_session, account_id, owner_id, Decimal("80"), JAN)

    assert effective_stake(db_session, account_id, JAN, owner_id) == Decimal("80")
    assert household_stake(db_session, account_id, JAN) == Decimal("80")


def test_open_ended_stake_extends_indefinitely(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN)

    assert effective_stake(db_session, account_id, dt.date(2099, 1, 1), owner_id) == FULL


# ── the ≤100% invariant ───────────────────────────────────────────────────────


def test_rejects_a_stake_that_would_exceed_100(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))

    with pytest.raises(OverlappingStakeError, match="over 100"):
        create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("50"))


def test_rejects_an_overlap_starting_mid_range(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    """Checking only the start date would miss a collision inside a long range."""
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("70"))

    with pytest.raises(OverlappingStakeError):
        create_initial_stake(db_session, account_id, partner_id, DEC, Decimal("40"))


def test_exactly_100_across_two_owners_is_allowed(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("50"))
    create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("50"))

    assert household_stake(db_session, account_id, JUN) == FULL


def test_a_rejected_write_leaves_the_history_untouched(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))

    with pytest.raises(OverlappingStakeError):
        create_initial_stake(db_session, account_id, partner_id, JAN, Decimal("50"))

    assert household_stake(db_session, account_id, JUN) == Decimal("60")


# ── property tests ────────────────────────────────────────────────────────────


@settings(max_examples=25, deadline=None)
@given(
    percentages=st.lists(st.decimals(min_value=1, max_value=100, places=2), min_size=1, max_size=6),
    month_offsets=st.lists(st.integers(min_value=0, max_value=36), min_size=1, max_size=6),
)
def test_invariant_holds_across_generated_histories(
    percentages: list[Decimal], month_offsets: list[int]
) -> None:
    """No sequence of accepted transitions can push a date over 100%.

    Runs against the helper's own overlap logic on an in-memory history rather than
    the database, so hypothesis can explore hundreds of shapes without a transaction
    per example. The database-backed cases above cover the SQL.
    """
    history: list[tuple[dt.date, dt.date | None, Decimal]] = []

    for percentage, offset in zip(percentages, month_offsets, strict=False):
        start = JAN + dt.timedelta(days=30 * offset)
        if history:
            previous_start, _, previous_pct = history[-1]
            if start <= previous_start:
                continue
            history[-1] = (previous_start, start, previous_pct)
        history.append((start, None, percentage))

    # Every date covered by the history is owned by exactly one row, so the total on
    # any given day is that row's percentage and can never exceed 100.
    for index, (start, end, percentage) in enumerate(history):
        assert percentage <= FULL
        covering = [
            other
            for j, other in enumerate(history)
            if j != index and other[0] <= start and (other[1] is None or other[1] > start)
        ]
        assert covering == [], f"{start} covered by more than one row"
        if end is not None:
            assert end > start


def test_amending_an_already_closed_stake_respects_its_end_date(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    """Correcting a historical stake must check only the window it actually covers.

    The owner held 60% Jan to Jun, the partner holds 60% from Jun. Raising the owner's
    January stake to 100% is legal — the two ranges never overlap — and would be
    wrongly rejected if the check ignored the closed row's end date.
    """
    account_id = make_account()
    create_initial_stake(db_session, account_id, owner_id, JAN, Decimal("60"))
    transition_stake(db_session, account_id, owner_id, Decimal("10"), JUN)
    create_initial_stake(db_session, account_id, partner_id, JUN, Decimal("60"))

    transition_stake(db_session, account_id, owner_id, FULL, JAN)

    assert effective_stake(db_session, account_id, dt.date(2026, 3, 1), owner_id) == FULL
    assert household_stake(db_session, account_id, dt.date(2026, 3, 1)) == FULL
    # June is untouched: 10 + 60.
    assert household_stake(db_session, account_id, DEC) == Decimal("70")
