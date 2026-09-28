"""Spend comparison, monthly trends and top merchants, with figures worked out by hand."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.schemas.advisor import LookupStatus
from app.schemas.common import ViewScope
from app.services.analysis import numbers
from app.services.analysis.periods import PeriodPreset, resolve
from app.services.analysis.spend_trends import compare, monthly, normalise_merchant, top_merchants

D = dt.date
Tx = Callable[..., int]


@pytest.fixture
def card(make_account: Callable[..., int]) -> int:
    return make_account(name="Card", kind="liability", subtype="credit_card")


def ctx_at(db_session: Session, owner_id: int, today: dt.date) -> ToolContext:
    return ToolContext(
        today=today, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )


def call(ctx: ToolContext, tool: str, **args: Any) -> dict[str, Any]:
    outcome = load_all().run(tool, args, ctx)
    assert outcome.status is LookupStatus.OK, outcome.content
    body: dict[str, Any] = json.loads(outcome.content)
    return body


def figure(text: str) -> str:
    return text.split(" [")[0]


# ── numbers ───────────────────────────────────────────────────────────────────


def test_numbers_round_once_half_up() -> None:
    assert numbers.quantize_money(Decimal("617.285")) == Decimal("617.29")
    assert numbers.ratio_bps(Decimal("40"), Decimal("51")) == 7843
    assert numbers.ratio_bps(Decimal("1"), Decimal("0")) is None
    assert numbers.change_bps(Decimal("450"), Decimal("300")) == 5000
    assert numbers.change_bps(Decimal("150"), Decimal("300")) == -5000
    assert numbers.change_bps(Decimal("5"), Decimal("0")) is None
    assert numbers.median([Decimal("1"), Decimal("4"), Decimal("2")]) == Decimal("2")
    assert numbers.median([Decimal("1.00"), Decimal("2.00")]) == Decimal("1.50")
    assert numbers.tenths(Decimal("23.45")) == 235


# ── comparison ────────────────────────────────────────────────────────────────


@pytest.fixture
def quarters(card: int, make_transaction: Tx, category_ids: dict[str, int]) -> None:
    """$100 of groceries on the 10th of each month in Q2, $150 in Q3."""
    for month, amount in [(4, "-100.00"), (5, "-100.00"), (6, "-100.00")]:
        make_transaction(card, D(2026, month, 10), amount, "GROCER", category_ids["Groceries"])
    for month in (7, 8, 9):
        make_transaction(card, D(2026, month, 10), "-150.00", "GROCER", category_ids["Groceries"])


def test_calendar_quarters_compare_whole(db_session: Session, quarters: None) -> None:
    today = D(2026, 10, 5)
    result = compare(
        db_session,
        resolve(PeriodPreset.LAST_QUARTER, today),
        resolve(PeriodPreset.CUSTOM, today, D(2026, 4, 1), D(2026, 6, 30)),
    )

    assert (result.total_a, result.total_b) == (Decimal("450.00"), Decimal("300.00"))
    assert result.total_change == Decimal("150.00")
    assert result.total_change_bps == 5000
    assert not result.like_for_like


def test_a_partial_quarter_is_compared_like_for_like(db_session: Session, quarters: None) -> None:
    today = D(2026, 8, 20)
    result = compare(
        db_session,
        resolve(PeriodPreset.THIS_QUARTER, today),
        resolve(PeriodPreset.LAST_QUARTER, today),
    )

    assert result.like_for_like
    assert (result.b.start, result.b.end) == (D(2026, 4, 1), D(2026, 5, 21))
    # July and August against April and May: 300 against 200, and all of Q2 was 300.
    assert (result.total_a, result.total_b) == (Decimal("300.00"), Decimal("200.00"))
    assert result.b_full_total == Decimal("300.00")


def test_spend_compare_tool(db_session: Session, owner_id: int, quarters: None) -> None:
    body = call(
        ctx_at(db_session, owner_id, D(2026, 8, 20)),
        "spend_compare",
        period_a={"preset": "this_quarter"},
        period_b={"preset": "last_quarter"},
    )
    data = body["data"]

    assert data["like_for_like"] is True
    assert figure(data["total_change"]) == "$100.00"
    assert figure(data["total_change_pct"]) == "50.00%"
    assert figure(data["period_b_whole"]) == "$300.00"
    assert data["rows"][0]["category_name_text"] == "Groceries"
    assert figure(data["rows"][0]["change"]) == "$100.00"


# ── monthly trend ─────────────────────────────────────────────────────────────


@pytest.fixture
def eateries(card: int, make_transaction: Tx, category_ids: dict[str, int]) -> None:
    """Restaurants: $100 a month December to May, then $150.00, $100, $150.01."""
    months = [D(2025, 12, 5)] + [D(2026, m, 5) for m in range(1, 9)]
    amounts = ["100.00"] * 6 + ["150.00", "100.00", "150.01"]
    for day, amount in zip(months, amounts, strict=True):
        make_transaction(card, day, f"-{amount}", "BISTRO", category_ids["Restaurants"])


def test_the_anomaly_edges(
    db_session: Session, eateries: None, category_ids: dict[str, int]
) -> None:
    trend = monthly(db_session, D(2026, 9, 15), 3, category_ids["Restaurants"])

    assert [p.month for p in trend.months] == [D(2026, 6, 1), D(2026, 7, 1), D(2026, 8, 1)]
    assert [p.trailing_median for p in trend.months] == [Decimal("100.00")] * 3
    # $150.00 against a $100 median is exactly 1.5x — not over it.
    assert [p.anomaly for p in trend.months] == [False, False, True]


def test_the_excess_floor(
    db_session: Session, card: int, make_transaction: Tx, category_ids: dict[str, int]
) -> None:
    """Over 1.5x the median but only $11 over it: noise, not a spike."""
    for month in range(1, 8):
        make_transaction(card, D(2026, month, 5), "-20.00", "CAFE", category_ids["Restaurants"])
    make_transaction(card, D(2026, 8, 5), "-31.00", "CAFE", category_ids["Restaurants"])

    trend = monthly(db_session, D(2026, 9, 15), 1, category_ids["Restaurants"])

    assert trend.months[-1].spend == Decimal("31.00")
    assert trend.months[-1].anomaly is False


def test_a_month_without_data_is_missing_not_zero(
    db_session: Session, card: int, make_transaction: Tx, category_ids: dict[str, int]
) -> None:
    for month in (1, 2, 4, 5, 6):
        make_transaction(card, D(2026, month, 5), "-80.00", "GROCER", category_ids["Groceries"])

    trend = monthly(db_session, D(2026, 7, 10), 4)

    by_month = {p.month.month: p.spend for p in trend.months}
    assert by_month == {3: None, 4: Decimal("80.00"), 5: Decimal("80.00"), 6: Decimal("80.00")}


def test_spend_trend_tool(
    db_session: Session, owner_id: int, eateries: None, category_ids: dict[str, int]
) -> None:
    body = call(
        ctx_at(db_session, owner_id, D(2026, 9, 15)),
        "spend_trend",
        category_id=category_ids["Restaurants"],
        months=3,
    )
    months = body["data"]["months"]

    assert [m["month"] for m in months] == ["2026-06", "2026-07", "2026-08"]
    assert figure(months[-1]["spend"]) == "$150.01"
    assert figure(months[-1]["trailing_median"]) == "$100.00"
    assert months[-1]["anomaly"] is True


def test_an_unknown_category_is_refused(db_session: Session, owner_id: int) -> None:
    outcome = load_all().run(
        "spend_trend", {"category_id": 999_999}, ctx_at(db_session, owner_id, D(2026, 9, 15))
    )

    assert outcome.status is LookupStatus.INVALID_ARGS
    assert "categories_list" in outcome.content


# ── merchants ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("SQ *BLUE BOTTLE #12", "BLUE BOTTLE"),
        ("Blue Bottle 0443", "BLUE BOTTLE"),
        ("TST* SWEETGREEN 123", "SWEETGREEN"),
        ("PAYPAL *SPOTIFY", "SPOTIFY"),
        ("CORNER MARKET #1234", "CORNER MARKET"),
        ("Whole Foods Market 10234", "WHOLE FOODS MARKET"),
        ("AMZN Mktp US*2K4AB", "AMZN MKTP US"),
        ("  corner   market ", "CORNER MARKET"),
        ("", "UNKNOWN MERCHANT"),
    ],
)
def test_merchant_normalisation(raw: str, normalised: str) -> None:
    assert normalise_merchant(raw) == normalised


def test_top_merchants_merge_and_share(
    db_session: Session, card: int, make_transaction: Tx, category_ids: dict[str, int]
) -> None:
    make_transaction(card, D(2026, 3, 4), "-52.30", "CORNER MARKET", category_ids["Groceries"])
    make_transaction(card, D(2026, 3, 9), "12.30", "CORNER MARKET", category_ids["Groceries"])
    make_transaction(
        card, D(2026, 3, 11), "-5.00", "SQ *BLUE BOTTLE #12", category_ids["Restaurants"]
    )
    make_transaction(card, D(2026, 3, 12), "-6.00", "Blue Bottle 0443", category_ids["Restaurants"])

    rows, total = top_merchants(
        db_session, resolve(PeriodPreset.CUSTOM, D(2026, 4, 1), D(2026, 3, 1), D(2026, 3, 31))
    )

    assert total == Decimal("51.00")
    assert [(r.name, r.count, r.spend, r.share_bps) for r in rows] == [
        ("CORNER MARKET", 2, Decimal("40.00"), 7843),
        ("BLUE BOTTLE", 2, Decimal("11.00"), 2157),
    ]
