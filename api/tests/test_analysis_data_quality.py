"""Data health on 15 April 2026.

- Checking's balance is from 15 January — exactly 90 days, not stale. Savings' is from
  14 January — 91 days, stale.
- The card's last transaction is 10 March, 36 days ago.
- March spending: $40.00 of groceries and $61.00 uncategorised — 60.40% uncategorised.
- February holds the transfer-pair cases: one true pair, three near misses, a pair already
  marked, a pair categorised as a transfer, and one outflow with three candidates.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.advisor.tools import ToolContext, load_all, savepoint_read_only
from app.models.transaction import Transaction
from app.schemas.common import ViewScope
from app.services.analysis.data_quality import health
from app.services.balances import record_balance

TODAY = dt.date(2026, 4, 15)
D = dt.date


@pytest.fixture
def world(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> dict[str, int]:
    ids = {
        "checking": make_account(name="Checking"),
        "savings": make_account(name="Savings", subtype="savings"),
        "card": make_account(name="Card", kind="liability", subtype="credit_card"),
        "brokerage": make_account(name="Brokerage", subtype="brokerage"),
    }
    record_balance(db_session, ids["checking"], D(2026, 1, 15), Decimal("5000.00"))
    record_balance(db_session, ids["savings"], D(2026, 1, 14), Decimal("9000.00"))

    tx = make_transaction
    tx(ids["card"], D(2026, 3, 5), "-40.00", "GROCER", category_ids["Groceries"])
    tx(ids["card"], D(2026, 3, 10), "-61.00", "PETROL PLUS")

    ids["pair_out"] = tx(ids["checking"], D(2026, 2, 10), "-1500.00", "TO SAVINGS")
    ids["pair_in"] = tx(ids["savings"], D(2026, 2, 11), "1500.00", "FROM CHECKING")
    # Near misses: a cent apart, the same account, four days apart.
    tx(ids["checking"], D(2026, 2, 12), "-800.00", "X")
    tx(ids["savings"], D(2026, 2, 12), "799.99", "X")
    tx(ids["checking"], D(2026, 2, 13), "-600.00", "X")
    tx(ids["checking"], D(2026, 2, 13), "600.00", "X")
    tx(ids["checking"], D(2026, 2, 1), "-700.00", "X")
    tx(ids["savings"], D(2026, 2, 5), "700.00", "X")
    # Already marked, and already categorised as a transfer.
    for account, amount in ((ids["checking"], "-900.00"), (ids["savings"], "900.00")):
        db_session.add(
            Transaction(
                account_id=account,
                posted_at=D(2026, 2, 14),
                amount=Decimal(amount),
                merchant="MARKED",
                transfer_group_id="g1",
            )
        )
    payment = category_ids["Credit Card Payment"]
    tx(ids["checking"], D(2026, 2, 15), "-1000.00", "PAYMENT", payment)
    tx(ids["card"], D(2026, 2, 15), "1000.00", "PAYMENT", payment)
    # One outflow, three candidates: two a day away, one five days away.
    ids["contested_out"] = tx(ids["checking"], D(2026, 2, 20), "-500.00", "OUT")
    ids["contested_first"] = tx(ids["savings"], D(2026, 2, 19), "500.00", "IN")
    tx(ids["brokerage"], D(2026, 2, 21), "500.00", "IN")
    tx(ids["brokerage"], D(2026, 2, 25), "500.00", "IN")
    db_session.flush()
    return ids


def test_staleness_and_freshness(db_session: Session, world: dict[str, int]) -> None:
    accounts = {a.account.id: a for a in health(db_session, TODAY).accounts}

    assert accounts[world["checking"]].balance_stale is False
    assert accounts[world["savings"]].balance_stale is True
    assert accounts[world["card"]].last_snapshot is None
    assert accounts[world["card"]].last_transaction == D(2026, 3, 10)


def test_uncategorised_share_of_last_month(db_session: Session, world: dict[str, int]) -> None:
    result = health(db_session, TODAY)

    assert result.month == D(2026, 3, 1)
    assert (result.uncategorised_count, result.uncategorised_spend, result.month_spend) == (
        1,
        Decimal("61.00"),
        Decimal("101.00"),
    )
    assert result.uncategorised_share_bps == 6040


def test_only_true_pairs_are_suggested(db_session: Session, world: dict[str, int]) -> None:
    pairs = {(p.outflow.id, p.inflow.id) for p in health(db_session, TODAY).pairs}

    assert pairs == {
        (world["pair_out"], world["pair_in"]),
        (world["contested_out"], world["contested_first"]),
    }


def test_the_tool(db_session: Session, owner_id: int, world: dict[str, int]) -> None:
    ctx = ToolContext(
        today=TODAY, user_id=owner_id, view=ViewScope.MINE, sessions=savepoint_read_only(db_session)
    )

    data = json.loads(load_all().run("data_health", {}, ctx).content)["data"]

    card = next(a for a in data["accounts"] if a["account_id"] == world["card"])
    assert card["days_since_transaction"] == 36
    assert data["stale_balance_count"] == 1
    assert data["uncategorised_last_month"]["share_pct"].startswith("60.40% [")
    first = data["possible_unmarked_transfers"][-1]
    assert first["amount"].startswith("$1,500.00 [")
    assert (first["from_account_name_text"], first["to_account_name_text"]) == (
        "Checking",
        "Savings",
    )
