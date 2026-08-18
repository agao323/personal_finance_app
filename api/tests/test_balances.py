"""Tests for the balance write path and point-in-time lookup.

The staleness boundary and `closed_at` get the most attention here: together they are
what stop carry-forward from keeping a sold car in net worth for ever, and both fail
silently if they regress.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import DataSource
from app.services.balances import (
    STALE_AFTER,
    balance_in_force,
    current_balance,
    record_balance,
)

JAN = dt.date(2026, 1, 1)
FEB = dt.date(2026, 2, 1)
MAR = dt.date(2026, 3, 1)


# ── writing ───────────────────────────────────────────────────────────────────


def test_records_a_snapshot(db_session: Session, make_account: Callable[..., int]) -> None:
    account_id = make_account()

    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.balance == Decimal("1000.00")


def test_same_day_write_overwrites_rather_than_duplicating(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Correcting a typo is one call; re-importing a file changes nothing."""
    account_id = make_account()

    record_balance(db_session, account_id, JAN, Decimal("1000.00"))
    record_balance(db_session, account_id, JAN, Decimal("1250.00"))

    count = db_session.execute(
        text("SELECT count(*) FROM balance_snapshots WHERE account_id = :a"),
        {"a": account_id},
    ).scalar_one()
    assert count == 1

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.balance == Decimal("1250.00")


def test_source_is_recorded_and_updated(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()

    record_balance(db_session, account_id, JAN, Decimal("10.00"), DataSource.MANUAL)
    record_balance(db_session, account_id, JAN, Decimal("20.00"), DataSource.CSV)

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.source == DataSource.CSV


def test_out_of_order_inserts_resolve_by_date_not_insertion_order(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Backfilling history must not make the oldest write win."""
    account_id = make_account()

    record_balance(db_session, account_id, MAR, Decimal("300.00"))
    record_balance(db_session, account_id, JAN, Decimal("100.00"))
    record_balance(db_session, account_id, FEB, Decimal("200.00"))

    for day, expected in [(JAN, "100.00"), (FEB, "200.00"), (MAR, "300.00")]:
        found = balance_in_force(db_session, account_id, day)
        assert found is not None
        assert found.balance == Decimal(expected), day


def test_balance_keeps_two_decimal_places(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1234.567"))

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.balance == Decimal("1234.57")


def test_liability_balances_are_stored_positive(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Net worth subtracts them. A negative here would make every total ambiguous."""
    account_id = make_account(name="Card", kind="liability", subtype="credit_card")
    record_balance(db_session, account_id, JAN, Decimal("2500.00"))

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.balance == Decimal("2500.00")


# ── carry-forward ─────────────────────────────────────────────────────────────


def test_carries_forward_between_snapshots(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Nobody records every account every day, so gaps are the normal case."""
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    found = balance_in_force(db_session, account_id, dt.date(2026, 1, 20))
    assert found is not None
    assert found.balance == Decimal("1000.00")
    assert found.as_of == JAN  # reports where the value came from
    assert not found.is_stale


def test_nothing_before_the_first_snapshot(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Zero would make a newly-added account look like it lost a fortune."""
    account_id = make_account()
    record_balance(db_session, account_id, FEB, Decimal("1000.00"))

    assert balance_in_force(db_session, account_id, JAN) is None


def test_account_with_no_snapshots_returns_nothing(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    assert balance_in_force(db_session, make_account(), JAN) is None


def test_unknown_account_returns_nothing(db_session: Session) -> None:
    assert balance_in_force(db_session, 999_999, JAN) is None


# ── staleness boundary ────────────────────────────────────────────────────────


def test_not_stale_exactly_at_the_cap(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    found = balance_in_force(db_session, account_id, JAN + STALE_AFTER)
    assert found is not None
    assert not found.is_stale


def test_stale_one_day_past_the_cap(db_session: Session, make_account: Callable[..., int]) -> None:
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    found = balance_in_force(db_session, account_id, JAN + STALE_AFTER + dt.timedelta(days=1))
    assert found is not None
    assert found.is_stale


def test_stale_values_are_flagged_not_dropped(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Omitting them would make net worth quietly drop instead of showing a warning."""
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))

    found = balance_in_force(db_session, account_id, JAN + dt.timedelta(days=365))
    assert found is not None
    assert found.balance == Decimal("1000.00")
    assert found.is_stale


def test_a_newer_snapshot_clears_staleness(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    record_balance(db_session, account_id, JAN, Decimal("1000.00"))
    later = JAN + dt.timedelta(days=200)
    record_balance(db_session, account_id, later, Decimal("1100.00"))

    found = balance_in_force(db_session, account_id, later)
    assert found is not None
    assert not found.is_stale
    assert found.balance == Decimal("1100.00")


# ── closed accounts ───────────────────────────────────────────────────────────


def test_closed_account_returns_nothing_on_the_close_date(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """The sold-car case. Carry-forward would otherwise keep it for ever."""
    account_id = make_account(name="Car", kind="illiquid_asset", subtype="vehicle", closed_at=FEB)
    record_balance(db_session, account_id, JAN, Decimal("15000.00"))

    assert balance_in_force(db_session, account_id, FEB) is None


def test_closed_account_still_resolves_before_it_closed(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """History stays intact — the chart must still show the car when you owned it."""
    account_id = make_account(name="Car", kind="illiquid_asset", subtype="vehicle", closed_at=FEB)
    record_balance(db_session, account_id, JAN, Decimal("15000.00"))

    found = balance_in_force(db_session, account_id, JAN)
    assert found is not None
    assert found.balance == Decimal("15000.00")


def test_closed_account_returns_nothing_afterwards(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account(name="Loan", kind="liability", subtype="auto_loan", closed_at=FEB)
    record_balance(db_session, account_id, JAN, Decimal("5000.00"))

    assert balance_in_force(db_session, account_id, MAR) is None


# ── current ───────────────────────────────────────────────────────────────────


def test_current_balance_uses_the_latest_snapshot(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    today = dt.date.today()
    record_balance(db_session, account_id, today - dt.timedelta(days=10), Decimal("900.00"))
    record_balance(db_session, account_id, today, Decimal("950.00"))

    found = current_balance(db_session, account_id)
    assert found is not None
    assert found.balance == Decimal("950.00")


def test_current_balance_is_not_stored_on_the_account(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Derived, never duplicated — a second source of truth can disagree silently."""
    columns = {
        row[0]
        for row in db_session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'accounts'")
        )
    }
    assert "balance" not in columns
    assert "current_balance" not in columns


@pytest.mark.parametrize("days_ago", [0, 1, 45, 89, 90])
def test_recent_snapshots_are_never_stale(
    db_session: Session, make_account: Callable[..., int], days_ago: int
) -> None:
    account_id = make_account()
    today = dt.date.today()
    record_balance(db_session, account_id, today - dt.timedelta(days=days_ago), Decimal("10.00"))

    found = current_balance(db_session, account_id)
    assert found is not None
    assert not found.is_stale
