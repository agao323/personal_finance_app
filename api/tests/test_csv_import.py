"""Tests for CSV import.

Idempotency is the acceptance criterion that matters. Duplicate transactions after a
re-import are the most common bug in this category of app, and the failure is quiet:
the totals drift and nothing errors.

Every fixture here is synthetic. No real export ever enters this directory.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.csv_import import (
    commit_import,
    derive_external_id,
    detect_mapping,
    parse_amount,
    plan_import,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _count(db_session: Session, account_id: int) -> int:
    return int(
        db_session.execute(
            text("SELECT count(*) FROM transactions WHERE account_id = :a"),
            {"a": account_id},
        ).scalar_one()
    )


# ── amounts ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("-4.75", "-4.75"),
        ("4.75", "4.75"),
        ("$1,234.56", "1234.56"),
        ("(62.10)", "-62.10"),
        ("1 234.56", "1234.56"),
    ],
)
def test_parse_amount(raw: str, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)


def test_amounts_are_never_parsed_as_float() -> None:
    """0.1 + 0.2 territory. A Decimal from the string is exact."""
    value = parse_amount("-0.30")
    assert isinstance(value, Decimal)
    assert value == Decimal("-0.30")


def test_inverting_flips_the_sign() -> None:
    """Institutions disagree about whether a debit is positive."""
    assert parse_amount("4.75", invert=True) == Decimal("-4.75")


def test_a_junk_amount_is_rejected_not_guessed(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    plan = plan_import(
        db_session,
        account_id,
        fixture("malformed_rows.csv"),
        detect_mapping(["Post Date", "Description", "Amount"]),
    )

    assert any(row.errors for row in plan.rows)
    assert plan.count("skip") >= 1


# ── the duplicate-row problem ─────────────────────────────────────────────────


def test_identical_rows_get_distinct_ids(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """Two coffees, same shop, same day, same amount — two real transactions.

    A content hash alone collapses them into one and silently eats a row.
    """
    account_id = make_account()
    first = derive_external_id(
        account_id, dt.date(2026, 3, 2), Decimal("-4.75"), "BLUEBIRD", None, 0
    )
    second = derive_external_id(
        account_id, dt.date(2026, 3, 2), Decimal("-4.75"), "BLUEBIRD", None, 1
    )

    assert first != second


def test_both_duplicate_rows_survive_an_import(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])

    commit_import(db_session, account_id, fixture("checking_outflows_negative.csv"), mapping)

    coffees = db_session.execute(
        text(
            "SELECT count(*) FROM transactions "
            "WHERE account_id = :a AND merchant = 'BLUEBIRD COFFEE'"
        ),
        {"a": account_id},
    ).scalar_one()
    assert coffees == 2


# ── idempotency ───────────────────────────────────────────────────────────────


def test_re_importing_the_same_file_changes_nothing(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """The acceptance criterion. Upsert, never insert."""
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])
    content = fixture("checking_outflows_negative.csv")

    first = commit_import(db_session, account_id, content, mapping)
    after_first = _count(db_session, account_id)

    second = commit_import(db_session, account_id, content, mapping)

    assert _count(db_session, account_id) == after_first
    assert first.created > 0
    assert second.created == 0


def test_re_importing_a_superset_adds_only_the_new_rows(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """The realistic case: this month's export contains last month's rows."""
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])

    commit_import(db_session, account_id, fixture("checking_outflows_negative.csv"), mapping)
    before = _count(db_session, account_id)

    result = commit_import(db_session, account_id, fixture("checking_superset.csv"), mapping)

    assert _count(db_session, account_id) > before
    assert result.created > 0


def test_source_provided_ids_are_used_as_the_key(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    mapping = detect_mapping(["Date", "Transaction ID", "Payee", "Notes", "Amount"])

    commit_import(db_session, account_id, fixture("with_source_ids.csv"), mapping)

    stored = db_session.execute(
        text("SELECT external_id FROM transactions WHERE account_id = :a ORDER BY id LIMIT 1"),
        {"a": account_id},
    ).scalar_one()
    assert stored == "TXN-00000001"


# ── preview ───────────────────────────────────────────────────────────────────


def test_preview_writes_nothing(db_session: Session, make_account: Callable[..., int]) -> None:
    """The safety net for importing a real export."""
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])

    plan = plan_import(db_session, account_id, fixture("checking_outflows_negative.csv"), mapping)

    assert plan.count("create") > 0
    assert _count(db_session, account_id) == 0


def test_preview_marks_rows_that_already_exist(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])
    content = fixture("checking_outflows_negative.csv")
    commit_import(db_session, account_id, content, mapping)

    plan = plan_import(db_session, account_id, content, mapping)

    assert plan.count("create") == 0
    assert plan.count("skip") > 0


def test_the_preview_is_the_plan_that_gets_executed(
    db_session: Session, make_account: Callable[..., int]
) -> None:
    """A preview showing something different from what commit does is worse than none."""
    account_id = make_account()
    mapping = detect_mapping(["Post Date", "Description", "Amount"])
    content = fixture("checking_outflows_negative.csv")

    plan = plan_import(db_session, account_id, content, mapping)
    result = commit_import(db_session, account_id, content, mapping)

    assert result.created == plan.count("create")


# ── mapping detection ─────────────────────────────────────────────────────────


def test_detects_a_simple_layout() -> None:
    mapping = detect_mapping(["Post Date", "Description", "Amount"])

    assert mapping.posted_at == "Post Date"
    assert mapping.amount == "Amount"


def test_detects_a_transaction_id_column() -> None:
    mapping = detect_mapping(["Date", "Transaction ID", "Payee", "Notes", "Amount"])

    assert mapping.external_id == "Transaction ID"
    assert mapping.merchant == "Payee"


# ── the endpoints ─────────────────────────────────────────────────────────────


def test_preview_endpoint(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()

    response = client.post(
        "/import/csv/preview",
        data={"account_id": str(account_id)},
        files={
            "file": (
                "export.csv",
                fixture("checking_outflows_negative.csv").encode(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["will_create"] > 0
    assert body["rows"]
    assert _count(db_session, account_id) == 0


def test_commit_endpoint_is_idempotent(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    payload = {
        "account_id": account_id,
        "mapping": {"posted_at": "Post Date", "amount": "Amount", "merchant": "Description"},
        "content": fixture("checking_outflows_negative.csv"),
    }

    first = client.post("/import/csv/commit", json=payload).json()
    second = client.post("/import/csv/commit", json=payload).json()

    assert first["created"] > 0
    assert second["created"] == 0


def test_commit_can_persist_the_mapping_for_reuse(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """Institutions never change their export shape; remembering it saves the step."""
    account_id = make_account()

    client.post(
        "/import/csv/commit",
        json={
            "account_id": account_id,
            "mapping": {"posted_at": "Post Date", "amount": "Amount"},
            "save_mapping_as": "Meridian checking",
            "content": fixture("checking_outflows_negative.csv"),
        },
    )

    saved = db_session.execute(
        text("SELECT name FROM import_mappings WHERE account_id = :a"), {"a": account_id}
    ).scalar_one()
    assert saved == "Meridian checking"
