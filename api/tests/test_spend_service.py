"""The spend helpers made public by ticket 082: `expense_rows` and `spend_totals`.

Analyses group spend their own way on top of these, so what they include and exclude is
pinned here directly: transfers and income out, refunds netted, uncategorised kept.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.spend import UNCATEGORISED, expense_rows, spend_by_category, spend_totals

MARCH = (dt.date(2026, 3, 1), dt.date(2026, 3, 31))


@pytest.fixture
def march(
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> dict[str, int]:
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    groceries = category_ids["Groceries"]
    return {
        "grocer": make_transaction(card, dt.date(2026, 3, 4), "-52.30", "CORNER MARKET", groceries),
        "refund": make_transaction(card, dt.date(2026, 3, 9), "12.30", "CORNER MARKET", groceries),
        "fuel": make_transaction(card, dt.date(2026, 3, 18), "-61.00", "PETROL PLUS"),
        "payment": make_transaction(
            card, dt.date(2026, 3, 20), "500.00", "PAYMENT", category_ids["Credit Card Payment"]
        ),
        "salary": make_transaction(
            card, dt.date(2026, 3, 1), "7400.00", "Payroll", category_ids["Salary"]
        ),
        "april": make_transaction(card, dt.date(2026, 4, 1), "-9.99", "STREAMLY"),
    }


def test_expense_rows_keep_spend_and_drop_transfers_income_and_other_months(
    db_session: Session, march: dict[str, int]
) -> None:
    rows = expense_rows(db_session, *MARCH)

    assert {t.id for t, _ in rows} == {march["grocer"], march["refund"], march["fuel"]}
    uncategorised = [t.id for t, category in rows if category is None]
    assert uncategorised == [march["fuel"]]


def test_spend_totals_net_the_refund_and_keep_uncategorised(
    db_session: Session, march: dict[str, int], category_ids: dict[str, int]
) -> None:
    totals = spend_totals(db_session, *MARCH)

    by_name = {name: amount for (_, name, _), amount in totals.items()}
    # $52.30 spent, $12.30 refunded: $40.00 of groceries.
    assert by_name == {"Groceries": Decimal("40.00"), UNCATEGORISED: Decimal("61.00")}


def test_spend_totals_agree_with_the_dashboard_rollup(
    db_session: Session, march: dict[str, int]
) -> None:
    """One set of rules: the public helper and the dashboard total cannot disagree."""
    totals = spend_totals(db_session, *MARCH)
    summary = spend_by_category(db_session, *MARCH)

    assert sum(totals.values(), Decimal("0.00")) == summary.total == Decimal("101.00")
