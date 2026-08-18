"""Tests for burn rate and runway.

Every test here is really about one thing: this number must not read *high*. A runway
that says eighteen months when it is really nine is worse than showing nothing, so the
partial-month and missing-data cases get the most attention — both fail in exactly
that direction if they regress.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.balances import record_balance
from app.services.ownership import create_initial_stake
from app.services.runway import (
    _complete_months_before,
    burn_window,
    liquid_assets,
    runway,
)

#: A fixed "today" so month arithmetic is deterministic regardless of when tests run.
TODAY = dt.date(2026, 6, 15)


@pytest.fixture
def groceries(db_session: Session) -> int:
    return int(
        db_session.execute(text("SELECT id FROM categories WHERE name = 'Groceries'")).scalar_one()
    )


def _spend(
    db_session: Session, account_id: int, posted: dt.date, amount: str, category_id: int
) -> None:
    db_session.execute(
        text(
            "INSERT INTO transactions (account_id, posted_at, amount, merchant, category_id) "
            "VALUES (:a, :d, :amt, 'Shop', :c)"
        ),
        {"a": account_id, "d": posted, "amt": Decimal(amount), "c": category_id},
    )


def _spend_in_month(
    db_session: Session, account_id: int, year: int, month: int, amount: str, category_id: int
) -> None:
    """One transaction mid-month, so it cannot land on a boundary by accident."""
    _spend(db_session, account_id, dt.date(year, month, 15), amount, category_id)


# ── the partial month ─────────────────────────────────────────────────────────


def test_complete_months_excludes_the_current_one(db_session: Session) -> None:
    months = _complete_months_before(TODAY, 3)

    assert [(s.year, s.month) for s, _ in months] == [(2026, 3), (2026, 4), (2026, 5)]
    # June — the month TODAY falls in — is absent.
    assert all(start.month != 6 for start, _ in months)


def test_month_bounds_cover_the_whole_month(db_session: Session) -> None:
    (start, end), *_ = _complete_months_before(dt.date(2026, 3, 10), 1)

    assert start == dt.date(2026, 2, 1)
    assert end == dt.date(2026, 2, calendar.monthrange(2026, 2)[1])


def test_a_partial_current_month_does_not_depress_burn(
    db_session: Session,
    make_account: Callable[..., int],
    groceries: int,
    owner_id: int,
) -> None:
    """The case the ticket is built around.

    Three complete months at $1,000, plus $80 so far in the current one. Averaging the
    partial month in gives $770 and reads as a third more runway than exists. The
    average must stay $1,000.
    """
    account_id = make_account()
    for month in (3, 4, 5):
        _spend_in_month(db_session, account_id, 2026, month, "-1000.00", groceries)
    _spend(db_session, account_id, dt.date(2026, 6, 5), "-80.00", groceries)

    average, counted, _ = burn_window(db_session, 3, TODAY)

    assert average == Decimal("1000.00")
    assert counted == 3


# ── missing data ──────────────────────────────────────────────────────────────


def test_a_month_with_no_data_is_skipped_not_counted_as_zero(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    """Missing data is not a month you spent nothing.

    Two months at $900 with a third empty. Counting the gap as zero gives $600 and
    inflates runway by half.
    """
    account_id = make_account()
    _spend_in_month(db_session, account_id, 2026, 4, "-900.00", groceries)
    _spend_in_month(db_session, account_id, 2026, 5, "-900.00", groceries)

    average, counted, _ = burn_window(db_session, 3, TODAY)

    assert average == Decimal("900.00")
    assert counted == 2


def test_no_data_at_all_reports_zero_burn(db_session: Session) -> None:
    average, counted, _ = burn_window(db_session, 3, TODAY)

    assert average == Decimal("0.00")
    assert counted == 0


# ── outliers ──────────────────────────────────────────────────────────────────


def test_a_one_off_purchase_is_excluded(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    """A car purchase should not triple the apparent burn rate.

    Five months at $1,000 and one at $40,000. Including it gives $7,500/month.
    """
    account_id = make_account()
    for month in (12, 1, 2, 3, 4):
        year = 2025 if month == 12 else 2026
        _spend_in_month(db_session, account_id, year, month, "-1000.00", groceries)
    _spend_in_month(db_session, account_id, 2026, 5, "-40000.00", groceries)

    average, counted, excluded = burn_window(db_session, 6, TODAY)

    assert average == Decimal("1000.00")
    assert counted == 5
    assert excluded == 1


def test_ordinary_variation_is_not_excluded(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    """The rule exists for one-offs, not for a slightly expensive month.

    900 / 1,000 / 1,400: median 1,000, threshold 3,000. All three stay.
    """
    account_id = make_account()
    for month, amount in ((3, "-900.00"), (4, "-1000.00"), (5, "-1400.00")):
        _spend_in_month(db_session, account_id, 2026, month, amount, groceries)

    average, counted, excluded = burn_window(db_session, 3, TODAY)

    assert counted == 3
    assert excluded == 0
    assert average == Decimal("1100.00")  # (900 + 1000 + 1400) / 3


def test_no_outlier_exclusion_with_fewer_than_three_months(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    """With two months one of them *is* the median; calling the other an outlier is noise."""
    account_id = make_account()
    _spend_in_month(db_session, account_id, 2026, 4, "-500.00", groceries)
    _spend_in_month(db_session, account_id, 2026, 5, "-9000.00", groceries)

    average, counted, excluded = burn_window(db_session, 3, TODAY)

    assert counted == 2
    assert excluded == 0
    assert average == Decimal("4750.00")


def test_the_outlier_multiple_is_configurable(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    account_id = make_account()
    for month, amount in ((3, "-1000.00"), (4, "-1000.00"), (5, "-2500.00")):
        _spend_in_month(db_session, account_id, 2026, month, amount, groceries)

    loose, _, loose_excluded = burn_window(db_session, 3, TODAY, Decimal("3"))
    strict, _, strict_excluded = burn_window(db_session, 3, TODAY, Decimal("2"))

    assert loose_excluded == 0
    assert strict_excluded == 1
    assert strict == Decimal("1000.00")
    assert loose == Decimal("1500.00")


# ── liquid assets ─────────────────────────────────────────────────────────────


def test_only_liquid_assets_count(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """A house is not runway."""
    cash = make_account(name="Savings")
    house = make_account(name="House", kind="illiquid_asset", subtype="real_estate")
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    for account_id in (cash, house, card):
        create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1))
        record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("50000.00"))

    assert liquid_assets(db_session, TODAY, owner_id) == Decimal("50000.00")


def test_liquid_assets_are_ownership_adjusted(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account(name="Joint savings")
    create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1), Decimal("60"))
    create_initial_stake(db_session, account_id, partner_id, dt.date(2026, 1, 1), Decimal("40"))
    record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("10000.00"))

    assert liquid_assets(db_session, TODAY, owner_id) == Decimal("6000.00")
    assert liquid_assets(db_session, TODAY, None) == Decimal("10000.00")


# ── the whole thing ───────────────────────────────────────────────────────────


def test_runway_divides_liquid_by_burn(
    db_session: Session, make_account: Callable[..., int], groceries: int, owner_id: int
) -> None:
    """$12,000 liquid against $1,000/month is twelve months."""
    savings = make_account(name="Savings")
    create_initial_stake(db_session, savings, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, savings, dt.date(2026, 1, 1), Decimal("12000.00"))
    for month in (3, 4, 5):
        _spend_in_month(db_session, savings, 2026, month, "-1000.00", groceries)

    result = runway(db_session, TODAY, owner_id)
    three = next(w for w in result.windows if w.months == 3)

    assert three.average_monthly_spend == Decimal("1000.00")
    assert three.months_of_runway == pytest.approx(12.0)


def test_zero_burn_reports_no_runway_rather_than_infinity(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    savings = make_account(name="Savings")
    create_initial_stake(db_session, savings, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, savings, dt.date(2026, 1, 1), Decimal("5000.00"))

    result = runway(db_session, TODAY, owner_id)

    assert all(w.months_of_runway is None for w in result.windows)


def test_all_three_windows_are_reported(db_session: Session) -> None:
    assert [w.months for w in runway(db_session, TODAY).windows] == [3, 6, 12]


# ── the endpoint ──────────────────────────────────────────────────────────────


def test_endpoint_returns_cents_and_flags_the_partial_month(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
) -> None:
    savings = make_account(name="Savings")
    create_initial_stake(db_session, savings, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, savings, dt.date(2026, 1, 1), Decimal("7500.00"))

    body = client.get("/runway").json()

    assert body["liquid_assets_cents"] == 750000
    # The UI says so on the tile; a runway whose definition is ambiguous is worse
    # than no runway.
    assert body["partial_month_excluded"] is True
    assert len(body["windows"]) == 3


def test_endpoint_honours_the_view(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    owner_id: int,
    partner_id: int,
) -> None:
    account_id = make_account(name="Joint")
    create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1), Decimal("50"))
    create_initial_stake(db_session, account_id, partner_id, dt.date(2026, 1, 1), Decimal("50"))
    record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("20000.00"))

    mine = client.get("/runway").json()
    household = client.get("/runway", params={"view": "household"}).json()

    assert mine["liquid_assets_cents"] == 1000000
    assert household["liquid_assets_cents"] == 2000000


def test_liquid_account_with_no_balance_is_skipped(
    db_session: Session, make_account: Callable[..., int], owner_id: int
) -> None:
    """An account opened but never funded contributes nothing, not zero-with-a-stake."""
    funded = make_account(name="Savings")
    empty = make_account(name="Opened, never funded")
    for account_id in (funded, empty):
        create_initial_stake(db_session, account_id, owner_id, dt.date(2026, 1, 1))
    record_balance(db_session, funded, dt.date(2026, 1, 1), Decimal("3000.00"))

    assert liquid_assets(db_session, TODAY, owner_id) == Decimal("3000.00")


def test_liquid_account_the_viewer_does_not_hold_is_skipped(
    db_session: Session, make_account: Callable[..., int], owner_id: int, partner_id: int
) -> None:
    account_id = make_account(name="Partner's savings")
    create_initial_stake(db_session, account_id, partner_id, dt.date(2026, 1, 1))
    record_balance(db_session, account_id, dt.date(2026, 1, 1), Decimal("9000.00"))

    assert liquid_assets(db_session, TODAY, owner_id) == Decimal("0.00")
    assert liquid_assets(db_session, TODAY, partner_id) == Decimal("9000.00")


def test_all_months_netting_to_refunds_keeps_the_data(
    db_session: Session, make_account: Callable[..., int], groceries: int
) -> None:
    """An outlier rule that discards every month has not found an outlier.

    With all-negative spend the median is negative, so `median x 3` is *more* negative
    than any value and the filter removes everything. Falling back to the unfiltered
    set is the only sane answer.
    """
    account_id = make_account()
    for month, amount in ((3, "100.00"), (4, "50.00"), (5, "10.00")):
        _spend_in_month(db_session, account_id, 2026, month, amount, groceries)

    average, counted, excluded = burn_window(db_session, 3, TODAY)

    assert counted == 3
    assert excluded == 0
    # Negative "spend" — three months of net refunds.
    assert average < Decimal("0.00")
