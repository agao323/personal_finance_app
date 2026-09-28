"""Recurring charges on 20 September 2026, against charges worked out by hand.

| Merchant | Rhythm | Amounts | Expect |
|---|---|---|---|
| STREAMLY | 3rd of each month, Oct 2025 to Sep 2026 | $15.49, then $17.99 from August | monthly, typical $15.49, +$2.50 (16.14%), $215.88 a year at the new price, next 4 Oct |
| CLOUDBOX | 15 Oct 2024, 14 Oct 2025 | $99.00 | annual — only seen with 24 months of lookback |
| JUICE BAR | Tuesdays, 7 Jul to 15 Sep 2026 | $6.75 | weekly, $351.00 a year |
| PEST CONTROL | 1 Oct, 1 Jan, 1 Apr, 1 Jul | $120.00 | quarterly, next 30 Sep |
| GYMCO | 5th of Nov 2025 to May 2026, then nothing | $40.00 | monthly but **lapsed** |
| HARDWARE STORE | 2 Jan, 20 Jan, 11 Apr, 30 Aug | various | not recurring |
"""  # noqa: E501

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope
from app.services.analysis.recurring import active_annual_total, find

TODAY = dt.date(2026, 9, 20)
D = dt.date


@pytest.fixture
def charges(
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    subs = category_ids["Subscriptions"]

    def charge(day: dt.date, amount: str, merchant: str, category: int | None = subs) -> None:
        make_transaction(card, day, f"-{amount}", merchant, category)

    months = [(2025, m) for m in (10, 11, 12)] + [(2026, m) for m in range(1, 10)]
    for year, month in months:
        price = "17.99" if (year, month) >= (2026, 8) else "15.49"
        charge(D(year, month, 3), price, "STREAMLY")
    make_transaction(card, D(2026, 8, 10), "17.99", "STREAMLY", subs)  # a refund, not a charge

    charge(D(2024, 10, 15), "99.00", "CLOUDBOX")
    charge(D(2025, 10, 14), "99.00", "CLOUDBOX")

    tuesday = D(2026, 7, 7)
    while tuesday <= D(2026, 9, 15):
        charge(tuesday, "6.75", "JUICE BAR", category_ids["Restaurants"])
        tuesday += dt.timedelta(days=7)

    for day in (D(2025, 10, 1), D(2026, 1, 1), D(2026, 4, 1), D(2026, 7, 1)):
        charge(day, "120.00", "PEST CONTROL", None)

    for year, month in [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 6)]:
        charge(D(year, month, 5), "40.00", "GYMCO")

    for day, amount in [
        (D(2026, 1, 2), "54.10"),
        (D(2026, 1, 20), "12.99"),
        (D(2026, 4, 11), "88.40"),
        (D(2026, 8, 30), "23.00"),
    ]:
        charge(day, amount, "HARDWARE STORE", None)


def test_what_repeats_is_found_and_what_does_not_is_not(db_session: Session, charges: None) -> None:
    found = {r.merchant: r for r in find(db_session, TODAY, 12)}

    assert set(found) == {"STREAMLY", "JUICE BAR", "PEST CONTROL", "GYMCO"}
    assert found["JUICE BAR"].cadence.name == "weekly"
    assert found["PEST CONTROL"].cadence.name == "quarterly"
    assert found["PEST CONTROL"].next_expected == D(2026, 9, 30)


def test_a_price_increase(db_session: Session, charges: None) -> None:
    streamly = next(r for r in find(db_session, TODAY, 12) if r.merchant == "STREAMLY")

    assert streamly.cadence.name == "monthly"
    assert streamly.charges == 12
    assert streamly.typical == Decimal("15.49")
    assert streamly.price_increase == Decimal("2.50")
    assert streamly.price_increase_bps == 1614
    assert streamly.annualised == Decimal("215.88")
    assert streamly.fixed_amount is False
    assert streamly.confidence == "medium"
    assert streamly.next_expected == D(2026, 10, 4)
    assert streamly.status == "active"


def test_a_stopped_subscription_is_lapsed_not_a_live_cost(
    db_session: Session, charges: None
) -> None:
    found = find(db_session, TODAY, 12)
    gym = next(r for r in found if r.merchant == "GYMCO")

    assert gym.status == "lapsed"
    assert found[-1] is gym
    # PEST CONTROL $480.00, JUICE BAR $351.00, STREAMLY $215.88 — the gym is not counted.
    assert active_annual_total(found) == Decimal("1046.88")


def test_an_annual_charge_needs_a_long_enough_look_back(db_session: Session, charges: None) -> None:
    short = {r.merchant for r in find(db_session, TODAY, 12)}
    long = {r.merchant: r for r in find(db_session, TODAY, 24)}

    assert "CLOUDBOX" not in short
    cloudbox = long["CLOUDBOX"]
    assert (cloudbox.cadence.name, cloudbox.annualised, cloudbox.confidence) == (
        "annual",
        Decimal("99.00"),
        "high",
    )
    assert cloudbox.next_expected == D(2026, 10, 13)


def test_the_tool(db_session: Session, owner_id: int, charges: None) -> None:
    ctx = ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )

    outcome = load_all().run("spend_recurring", {"lookback_months": 12}, ctx)
    data = json.loads(outcome.content)["data"]

    assert outcome.status is LookupStatus.OK
    assert data["active_annual_total"].startswith("$1,046.88 [")
    assert data["lapsed_count"] == 1
    streamly = next(c for c in data["charges"] if c["merchant_text"] == "STREAMLY")
    assert streamly["price_increase"].startswith("$2.50 [")
    assert streamly["price_increase_pct"].startswith("16.14% [")
    assert [c["merchant_text"] for c in data["charges"]] == [
        "PEST CONTROL",
        "JUICE BAR",
        "STREAMLY",
        "GYMCO",
    ]
