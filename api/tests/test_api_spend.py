"""Tests for spend rollups.

The transfer-exclusion tests are the ones that matter. A transfer appearing as
spending is not a small error — it makes every number on the dashboard suspect, and
it looks entirely plausible on a chart.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.spend import prior_period, spend_by_category

JAN = dt.date(2026, 1, 1)
JAN_END = dt.date(2026, 1, 31)
FEB = dt.date(2026, 2, 1)


@pytest.fixture
def categories(db_session: Session) -> dict[str, int]:
    """The ids of a few seeded categories, by name."""
    rows = db_session.execute(text("SELECT name, id FROM categories")).all()
    return {name: cid for name, cid in rows}


def _spend(
    db_session: Session,
    account_id: int,
    posted: dt.date,
    amount: str,
    category_id: int | None = None,
) -> None:
    """Record a transaction. Outflows are negative, matching the wire convention."""
    db_session.execute(
        text(
            "INSERT INTO transactions (account_id, posted_at, amount, merchant, category_id) "
            "VALUES (:a, :d, :amt, 'Shop', :c)"
        ),
        {"a": account_id, "d": posted, "amt": Decimal(amount), "c": category_id},
    )


# ── the exclusions ────────────────────────────────────────────────────────────


def test_transfers_are_excluded(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """The test this whole endpoint exists to pass.

    $2,000 moved to a brokerage is not $2,000 of spending.
    """
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "-2000.00", categories["Transfer"])

    summary = spend_by_category(db_session, JAN, JAN_END)

    assert summary.total == Decimal("60.00")
    assert summary.excluded_transfer_count == 1
    assert [b.category_name for b in summary.buckets] == ["Groceries"]


def test_income_is_excluded(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """Spend is spend. Netting income in would answer a different question."""
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "5000.00", categories["Salary"])

    summary = spend_by_category(db_session, JAN, JAN_END)

    assert summary.total == Decimal("60.00")


def test_uncategorised_appears_as_its_own_bucket(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """Dropping it would make the total quietly understate reality."""
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "-25.00", None)

    summary = spend_by_category(db_session, JAN, JAN_END)

    names = {b.category_name: b.spend for b in summary.buckets}
    assert names["Uncategorised"] == Decimal("25.00")
    assert summary.total == Decimal("85.00")


def test_spend_is_not_split_by_ownership(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """A $60 charge on a half-owned card is $60 of spend. The groceries were bought once."""
    from app.services.ownership import create_initial_stake

    account_id = make_account(name="Joint card", kind="liability", subtype="credit_card")
    create_initial_stake(db_session, account_id, 1, JAN, Decimal("50"))
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])

    assert spend_by_category(db_session, JAN, JAN_END).total == Decimal("60.00")


# ── rollups ───────────────────────────────────────────────────────────────────


def test_totals_per_category(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "-40.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "-15.50", categories["Restaurants"])

    summary = spend_by_category(db_session, JAN, JAN_END)

    totals = {b.category_name: b.spend for b in summary.buckets}
    assert totals == {"Groceries": Decimal("100.00"), "Restaurants": Decimal("15.50")}
    assert summary.total == Decimal("115.50")


def test_grouping_by_parent_category(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """Groceries and Restaurants both roll up into Food."""
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "-15.00", categories["Restaurants"])

    summary = spend_by_category(db_session, JAN, JAN_END, by_parent=True)

    totals = {b.category_name: b.spend for b in summary.buckets}
    assert totals == {"Food": Decimal("75.00")}


def test_buckets_are_ordered_largest_first(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-10.00", categories["Restaurants"])
    _spend(db_session, account_id, JAN, "-90.00", categories["Groceries"])

    summary = spend_by_category(db_session, JAN, JAN_END)

    assert [b.category_name for b in summary.buckets] == ["Groceries", "Restaurants"]


def test_a_refund_reduces_spend(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    """An inflow on an expense category is money you did not spend after all."""
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-100.00", categories["Groceries"])
    _spend(db_session, account_id, JAN, "30.00", categories["Groceries"])

    assert spend_by_category(db_session, JAN, JAN_END).total == Decimal("70.00")


# ── prior period ──────────────────────────────────────────────────────────────


def test_prior_period_is_equal_length_not_calendar(
    db_session: Session,
) -> None:
    """A 31-day January against a 28-day February would show a fake drop."""
    start, end = prior_period(dt.date(2026, 3, 1), dt.date(2026, 3, 31))

    assert (end - start) == (dt.date(2026, 3, 31) - dt.date(2026, 3, 1))
    assert end == dt.date(2026, 2, 28)


def test_prior_period_comparison_across_a_month_boundary(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, dt.date(2026, 1, 15), "-100.00", categories["Groceries"])
    _spend(db_session, account_id, dt.date(2026, 2, 15), "-160.00", categories["Groceries"])

    summary = spend_by_category(db_session, FEB, dt.date(2026, 2, 28))
    groceries = next(b for b in summary.buckets if b.category_name == "Groceries")

    assert groceries.spend == Decimal("160.00")
    assert groceries.prior_spend == Decimal("100.00")
    assert groceries.change == Decimal("60.00")


def test_range_boundaries_are_inclusive(
    db_session: Session, make_account: Callable[..., int], categories: dict[str, int]
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-10.00", categories["Groceries"])
    _spend(db_session, account_id, JAN_END, "-20.00", categories["Groceries"])
    _spend(db_session, account_id, FEB, "-99.00", categories["Groceries"])

    assert spend_by_category(db_session, JAN, JAN_END).total == Decimal("30.00")


# ── the endpoint ──────────────────────────────────────────────────────────────


def test_endpoint_returns_cents(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    categories: dict[str, int],
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.50", categories["Groceries"])

    body = client.get("/spend", params={"from": "2026-01-01", "to": "2026-01-31"}).json()

    assert body["total_cents"] == 6050
    assert body["buckets"][0]["spend_cents"] == 6050
    assert body["group_by"] == "category"


def test_endpoint_reports_excluded_transfers(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    categories: dict[str, int],
) -> None:
    """Visible rather than merely true — a silent exclusion is unverifiable."""
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-2000.00", categories["Transfer"])

    body = client.get("/spend", params={"from": "2026-01-01", "to": "2026-01-31"}).json()

    assert body["total_cents"] == 0
    assert body["excluded_transfer_count"] == 1


def test_endpoint_groups_by_parent(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    categories: dict[str, int],
) -> None:
    account_id = make_account()
    _spend(db_session, account_id, JAN, "-60.00", categories["Groceries"])

    body = client.get(
        "/spend",
        params={"from": "2026-01-01", "to": "2026-01-31", "group_by": "parent_category"},
    ).json()

    assert body["buckets"][0]["category_name"] == "Food"


def test_endpoint_defaults_to_month_to_date(client: TestClient) -> None:
    body = client.get("/spend").json()

    assert body["start"] == dt.date.today().replace(day=1).isoformat()
    assert body["end"] == dt.date.today().isoformat()


def test_endpoint_rejects_a_bad_grouping(client: TestClient) -> None:
    assert client.get("/spend", params={"group_by": "by_vibes"}).status_code == 422
