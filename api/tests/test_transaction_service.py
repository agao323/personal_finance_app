"""`services/transactions.search`, called directly.

The query behind the transactions screen, moved out of its router by ticket 082 so the
advisor's search runs the same one. `test_api_transactions.py` still covers the route.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.services.transactions import TransactionFilters, search


@pytest.fixture
def ledger(
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> dict[str, int]:
    card = make_account(name="Card", kind="liability", subtype="credit_card")
    checking = make_account(name="Checking")
    return {
        "card": card,
        "checking": checking,
        "grocer": make_transaction(
            card, dt.date(2026, 3, 4), "-52.30", "CORNER MARKET", category_ids["Groceries"]
        ),
        "fuel": make_transaction(card, dt.date(2026, 3, 18), "-61.00", "PETROL PLUS"),
        "salary": make_transaction(
            checking, dt.date(2026, 3, 1), "7400.00", "Payroll", category_ids["Salary"]
        ),
        "april": make_transaction(card, dt.date(2026, 4, 2), "-9.99", "STREAMLY"),
    }


def test_no_filters_returns_everything_newest_first(
    db_session: Session, ledger: dict[str, int]
) -> None:
    result = search(db_session, TransactionFilters(), limit=50, offset=0)

    ids = [t.id for t, _ in result.rows]
    assert ids == [ledger["april"], ledger["fuel"], ledger["grocer"], ledger["salary"]]
    assert result.total == 4


def test_filters_combine(db_session: Session, ledger: dict[str, int]) -> None:
    march_on_the_card = TransactionFilters(
        date_from=dt.date(2026, 3, 1), date_to=dt.date(2026, 3, 31), account_id=ledger["card"]
    )

    result = search(db_session, march_on_the_card, limit=50, offset=0)

    assert {t.id for t, _ in result.rows} == {ledger["grocer"], ledger["fuel"]}
    assert {name for _, name in result.rows} == {"Card"}


def test_uncategorised_is_three_valued(db_session: Session, ledger: dict[str, int]) -> None:
    only = search(db_session, TransactionFilters(uncategorised=True), limit=50, offset=0)
    none = search(db_session, TransactionFilters(uncategorised=False), limit=50, offset=0)

    assert {t.id for t, _ in only.rows} == {ledger["fuel"], ledger["april"]}
    assert {t.id for t, _ in none.rows} == {ledger["grocer"], ledger["salary"]}


def test_search_is_case_insensitive(db_session: Session, ledger: dict[str, int]) -> None:
    result = search(db_session, TransactionFilters(search="corner"), limit=50, offset=0)

    assert [t.id for t, _ in result.rows] == [ledger["grocer"]]


def test_the_total_ignores_the_page(db_session: Session, ledger: dict[str, int]) -> None:
    result = search(db_session, TransactionFilters(), limit=1, offset=1)

    assert [t.id for t, _ in result.rows] == [ledger["fuel"]]
    assert result.total == 4


def test_magnitude_bounds_ignore_the_sign(db_session: Session, ledger: dict[str, int]) -> None:
    """A $52.30 purchase is stored as -52.30; "about fifty dollars" must still find it."""
    from decimal import Decimal

    result = search(
        db_session,
        TransactionFilters(magnitude_min=Decimal("50.00"), magnitude_max=Decimal("62.00")),
        limit=50,
        offset=0,
    )

    assert {t.id for t, _ in result.rows} == {ledger["grocer"], ledger["fuel"]}
