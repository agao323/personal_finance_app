"""Tests for the categorisation rules engine.

The manual-override tests are why this ticket and 023 are paired. `category_source`
was designed in ticket 009 and nothing has written `'manual'` until now, so this is
the first time the protection is actually exercised rather than merely intended.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import MatchType
from app.models.transaction import CategorizationRule
from app.services.categorize import (
    apply_rules,
    has_nested_quantifier,
    validate_pattern,
)

JAN = dt.date(2026, 1, 1)


def _rule(
    db_session: Session,
    pattern: str,
    category_id: int,
    priority: int = 100,
    match_type: MatchType = MatchType.CONTAINS,
) -> CategorizationRule:
    rule = CategorizationRule(
        pattern=pattern, category_id=category_id, priority=priority, match_type=match_type
    )
    db_session.add(rule)
    db_session.flush()
    return rule


def _source_of(db_session: Session, transaction_id: int) -> tuple[int | None, str | None]:
    return db_session.execute(  # type: ignore[return-value]
        text("SELECT category_id, category_source FROM transactions WHERE id = :i"),
        {"i": transaction_id},
    ).one()


# ── the manual override ───────────────────────────────────────────────────────


def test_a_manual_category_survives_a_full_rule_run(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """The reason category_source exists at all.

    A human decided this transaction is Shopping. A rule says Groceries. Re-running
    the whole rule set over all history must leave the human's decision alone —
    unconditionally, not "unless the rule is newer".
    """
    account_id = make_account()
    transaction_id = make_transaction(
        account_id,
        JAN,
        "-40.00",
        merchant="AMBIGUOUS VENDOR",
        category_id=category_ids["Shopping"],
        category_source="manual",
    )
    _rule(db_session, "AMBIGUOUS", category_ids["Groceries"])

    result = apply_rules(db_session, only_uncategorised=False)

    category_id, source = _source_of(db_session, transaction_id)
    assert category_id == category_ids["Shopping"]
    assert source == "manual"
    assert result.manual_preserved == 1


def test_a_rule_category_is_replaced_by_a_later_run(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """Rule-assigned categories are not sacred — only human ones are."""
    account_id = make_account()
    transaction_id = make_transaction(
        account_id,
        JAN,
        "-40.00",
        merchant="COFFEE HOUSE",
        category_id=category_ids["Shopping"],
        category_source="rule",
    )
    _rule(db_session, "COFFEE", category_ids["Restaurants"])

    apply_rules(db_session, only_uncategorised=False)

    category_id, source = _source_of(db_session, transaction_id)
    assert category_id == category_ids["Restaurants"]
    assert source == "rule"


# ── matching ──────────────────────────────────────────────────────────────────


def test_first_match_by_priority_wins(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-20.00", merchant="SHELL FUEL MART")
    _rule(db_session, "FUEL", category_ids["Fuel"], priority=10)
    _rule(db_session, "MART", category_ids["Groceries"], priority=20)

    apply_rules(db_session)

    assert _source_of(db_session, transaction_id)[0] == category_ids["Fuel"]


@pytest.mark.parametrize(
    ("match_type", "pattern", "merchant", "expected"),
    [
        (MatchType.CONTAINS, "COFFEE", "BLUE COFFEE CO", True),
        (MatchType.EQUALS, "BLUE COFFEE CO", "BLUE COFFEE CO", True),
        (MatchType.EQUALS, "COFFEE", "BLUE COFFEE CO", False),
        (MatchType.STARTS_WITH, "BLUE", "BLUE COFFEE CO", True),
        (MatchType.STARTS_WITH, "COFFEE", "BLUE COFFEE CO", False),
        (MatchType.REGEX, r"^BLUE.*CO$", "BLUE COFFEE CO", True),
        (MatchType.REGEX, r"^RED", "BLUE COFFEE CO", False),
    ],
)
def test_match_types(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
    match_type: MatchType,
    pattern: str,
    merchant: str,
    expected: bool,
) -> None:
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-20.00", merchant=merchant)
    _rule(db_session, pattern, category_ids["Groceries"], match_type=match_type)

    apply_rules(db_session)

    matched = _source_of(db_session, transaction_id)[0] is not None
    assert matched is expected


def test_no_match_leaves_it_uncategorised(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """A real state the UI surfaces as a prompt to add a rule, not an error."""
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-20.00", merchant="MYSTERY")
    _rule(db_session, "NOTHING", category_ids["Groceries"])

    apply_rules(db_session)

    assert _source_of(db_session, transaction_id) == (None, None)


def test_re_running_is_idempotent(
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    make_transaction(account_id, JAN, "-20.00", merchant="COFFEE HOUSE")
    _rule(db_session, "COFFEE", category_ids["Restaurants"])

    first = apply_rules(db_session, only_uncategorised=False)
    second = apply_rules(db_session, only_uncategorised=False)

    assert first.categorised == 1
    assert second.categorised == 0


# ── untrusted patterns ────────────────────────────────────────────────────────


def test_a_malformed_regex_is_a_validation_error_not_a_500() -> None:
    """User-supplied patterns are untrusted input."""
    with pytest.raises(ValueError, match=r"[Ii]nvalid|regex"):
        validate_pattern("([unclosed", MatchType.REGEX)


def test_a_valid_regex_passes() -> None:
    validate_pattern(r"^ACME \d+$", MatchType.REGEX)


def test_a_literal_pattern_is_never_compiled() -> None:
    """Brackets are literal text under `contains`, not a broken regex."""
    validate_pattern("([unclosed", MatchType.CONTAINS)


# ── the endpoint ──────────────────────────────────────────────────────────────


def test_rules_crud(client: TestClient, category_ids: dict[str, int]) -> None:
    created = client.post(
        "/rules",
        json={"pattern": "COFFEE", "category_id": category_ids["Restaurants"], "priority": 10},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    assert any(r["id"] == rule_id for r in client.get("/rules").json())

    patched = client.patch(f"/rules/{rule_id}", json={"priority": 5})
    assert patched.json()["priority"] == 5

    assert client.delete(f"/rules/{rule_id}").status_code == 204
    assert not any(r["id"] == rule_id for r in client.get("/rules").json())


def test_endpoint_rejects_a_malformed_regex(
    client: TestClient, category_ids: dict[str, int]
) -> None:
    response = client.post(
        "/rules",
        json={
            "pattern": "([unclosed",
            "match_type": "regex",
            "category_id": category_ids["Groceries"],
        },
    )

    assert response.status_code == 422


def test_apply_endpoint_reports_what_it_did(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    make_transaction(account_id, JAN, "-20.00", merchant="COFFEE HOUSE")
    make_transaction(
        account_id,
        JAN,
        "-30.00",
        merchant="COFFEE HOUSE",
        category_id=category_ids["Shopping"],
        category_source="manual",
    )
    client.post("/rules", json={"pattern": "COFFEE", "category_id": category_ids["Restaurants"]})

    body = client.post("/rules/apply", json={"only_uncategorised": False}).json()

    assert body["categorised"] == 1
    assert body["manual_preserved"] == 1


def test_unknown_rule_is_a_404(client: TestClient) -> None:
    assert client.patch("/rules/999999", json={"priority": 1}).status_code == 404
    assert client.delete("/rules/999999").status_code == 404


# ── catastrophic backtracking ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern",
    [
        r"(a+)+$",
        r"(a*)*b",
        r"(\d+)+x",
        r"(ab+)+c",
        r"(a{1,})+",
    ],
)
def test_nested_quantifiers_are_rejected(pattern: str) -> None:
    """A pattern the user supplies runs against every transaction they own.

    `(a+)+` against a long non-matching string backtracks exponentially and pins a
    worker. The check is a heuristic, not a decision procedure — it catches the
    classic shape rather than proving anything.
    """
    assert has_nested_quantifier(pattern)

    with pytest.raises(ValueError, match="exponential"):
        validate_pattern(pattern, MatchType.REGEX)


@pytest.mark.parametrize(
    "pattern",
    [
        r"^ACME \d+$",
        r"COFFEE|TEA",
        r"[A-Z]{3,6}",
        r"(WHOLE FOODS|TRADER)",
        r"SQ \*\w+",
    ],
)
def test_ordinary_patterns_are_allowed(pattern: str) -> None:
    """The heuristic must not reject the patterns people actually write."""
    assert not has_nested_quantifier(pattern)
    validate_pattern(pattern, MatchType.REGEX)


def test_an_escaped_quantifier_is_not_a_quantifier() -> None:
    r"""`\(a\+\)+` is a literal "(a+)" repeated — not nested repetition."""
    assert not has_nested_quantifier(r"\(a\+\)+")


def test_a_character_class_containing_a_plus_is_literal() -> None:
    """Inside a class, `+` is a literal character rather than a quantifier."""
    assert not has_nested_quantifier(r"([a+])+")


# ── the match preview ─────────────────────────────────────────────────────────


def test_preview_reports_what_a_pattern_would_hit(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
) -> None:
    account_id = make_account()
    make_transaction(account_id, dt.date(2026, 3, 1), "-40.00", "CORNER MARKET")
    make_transaction(account_id, dt.date(2026, 3, 2), "-12.00", "Corner Market #2")
    make_transaction(account_id, dt.date(2026, 3, 3), "-90.00", "Petrol Station")

    body = client.post("/rules/preview", json={"pattern": "corner market"}).json()

    assert body["match_count"] == 2
    assert {row["merchant"] for row in body["matches"]} == {"CORNER MARKET", "Corner Market #2"}


def test_preview_matches_the_description_when_the_merchant_is_empty(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
) -> None:
    """A `LIKE` on the merchant column would agree with the engine until it didn't.

    `subject_of` falls back to the description when the merchant column is empty, which
    is how plenty of institutions export. A preview that queried the merchant column
    alone would report zero matches for a rule that goes on to match everything — a
    safety net that fails silently in exactly the case you needed it.
    """
    account_id = make_account()
    db_session.execute(
        text(
            "INSERT INTO transactions (account_id, posted_at, amount, merchant, description) "
            "VALUES (:a, :d, :amt, NULL, :desc)"
        ),
        {
            "a": account_id,
            "d": dt.date(2026, 3, 1),
            "amt": Decimal("-40.00"),
            "desc": "POS PURCHASE CORNER MARKET",
        },
    )

    body = client.post("/rules/preview", json={"pattern": "corner market"}).json()

    assert body["match_count"] == 1


def test_preview_counts_matches_it_would_not_change(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """A count that ignored manual rows would promise a run it will not deliver."""
    account_id = make_account()
    manual_id = make_transaction(account_id, dt.date(2026, 3, 1), "-40.00", "CORNER MARKET")
    make_transaction(account_id, dt.date(2026, 3, 2), "-12.00", "CORNER MARKET")
    client.patch(f"/transactions/{manual_id}", json={"category_id": category_ids["Groceries"]})

    body = client.post("/rules/preview", json={"pattern": "corner"}).json()

    assert body["match_count"] == 2
    assert body["already_manual"] == 1


def test_preview_caps_the_rows_it_returns_but_not_the_count(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
) -> None:
    account_id = make_account()
    for day in range(1, 6):
        make_transaction(account_id, dt.date(2026, 3, day), "-10.00", "CORNER MARKET")

    body = client.post("/rules/preview", json={"pattern": "corner", "limit": 2}).json()

    assert body["match_count"] == 5
    assert len(body["matches"]) == 2


def test_preview_rejects_a_catastrophic_pattern(client: TestClient) -> None:
    """Same validation as the write path — before it matters, not after."""
    response = client.post("/rules/preview", json={"pattern": "(a+)+b", "match_type": "regex"})

    assert response.status_code == 422


def test_preview_writes_nothing(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
) -> None:
    account_id = make_account()
    transaction_id = make_transaction(account_id, dt.date(2026, 3, 1), "-40.00", "CORNER MARKET")

    client.post("/rules/preview", json={"pattern": "corner"})

    rows = {row["id"]: row for row in client.get("/transactions").json()["items"]}
    assert rows[transaction_id]["category"] is None
