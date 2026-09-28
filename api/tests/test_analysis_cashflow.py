"""Cashflow on 10 July 2026, over six months worked out by hand.

| Month | Income | Spend | Net | Savings rate |
|---|---|---|---|---|
| Jan | $7,400.00 salary | $1,000.00 (a $2,000 transfer pair excluded) | $6,400.00 | 86.49% |
| Feb | $7,400.00 | $1,200.00 less a $200.00 refund = $1,000.00 | $6,400.00 | 86.49% |
| Mar | $1,000.00 interest | $1,500.00 | -$500.00 | -50.00% |
| Apr | no transactions at all | skipped | | |
| May | $7,400.00 + $2,600.00 bonus | $9,000.00 | $1,000.00 | 10.00% |
| Jun | none | $500.00 | -$500.00 | none |

Totals: income $25,800.00, spend $13,000.00, net $12,800.00, savings rate 49.61%.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.schemas.common import ViewScope
from app.services.analysis.cashflow import monthly

TODAY = dt.date(2026, 7, 10)
D = dt.date


@pytest.fixture
def ledger(
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    checking = make_account(name="Checking")
    brokerage = make_account(name="Brokerage", kind="liquid_asset", subtype="brokerage")
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    salary, groceries = category_ids["Salary"], category_ids["Groceries"]
    rows = [
        (checking, D(2026, 1, 1), "7400.00", salary),
        (card, D(2026, 1, 10), "-1000.00", groceries),
        (checking, D(2026, 1, 2), "-2000.00", category_ids["Investment Contribution"]),
        (brokerage, D(2026, 1, 2), "2000.00", category_ids["Investment Contribution"]),
        (checking, D(2026, 2, 1), "7400.00", salary),
        (card, D(2026, 2, 10), "-1200.00", groceries),
        (card, D(2026, 2, 12), "200.00", groceries),
        (checking, D(2026, 3, 31), "1000.00", category_ids["Interest"]),
        (card, D(2026, 3, 10), "-1500.00", groceries),
        (checking, D(2026, 5, 1), "7400.00", salary),
        (checking, D(2026, 5, 15), "2600.00", category_ids["Other Income"]),
        (card, D(2026, 5, 10), "-9000.00", groceries),
        (card, D(2026, 6, 10), "-500.00", groceries),
    ]
    for account, day, amount, category in rows:
        make_transaction(account, day, amount, "X", category)


def test_each_month(db_session: Session, ledger: None) -> None:
    flow = monthly(db_session, TODAY, 6)

    table = [(m.month.month, m.income, m.spend, m.net, m.savings_rate_bps) for m in flow.months]
    assert table == [
        (1, Decimal("7400.00"), Decimal("1000.00"), Decimal("6400.00"), 8649),
        (2, Decimal("7400.00"), Decimal("1000.00"), Decimal("6400.00"), 8649),
        (3, Decimal("1000.00"), Decimal("1500.00"), Decimal("-500.00"), -5000),
        (5, Decimal("10000.00"), Decimal("9000.00"), Decimal("1000.00"), 1000),
        (6, Decimal("0.00"), Decimal("500.00"), Decimal("-500.00"), None),
    ]
    assert flow.skipped == [D(2026, 4, 1)]


def test_the_window(db_session: Session, ledger: None) -> None:
    flow = monthly(db_session, TODAY, 6)

    assert (flow.income, flow.spend, flow.net) == (
        Decimal("25800.00"),
        Decimal("13000.00"),
        Decimal("12800.00"),
    )
    assert flow.savings_rate_bps == 4961


def test_the_tool(db_session: Session, owner_id: int, ledger: None) -> None:
    ctx = ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )

    data = json.loads(load_all().run("cashflow_get", {"months": 6}, ctx).content)["data"]

    assert data["months_without_data"] == ["2026-04"]
    assert data["savings_rate_pct"].startswith("49.61% [")
    assert data["total_net"].startswith("$12,800.00 [")
    march = next(m for m in data["months"] if m["month"] == "2026-03")
    assert march["savings_rate_pct"].startswith("-50.00% [")
    june = next(m for m in data["months"] if m["month"] == "2026-06")
    assert "savings_rate_pct" not in june
