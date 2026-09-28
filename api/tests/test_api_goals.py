"""Goals: each kind's rules, at the database and at the API; who sees what; the export.

The migration's round trip is `test_schema.test_upgrade_downgrade_upgrade_is_clean`, which walks
every revision including 0008.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import GoalKind
from app.models.goal import Goal

PARTNER = "partner@example.invalid"


@pytest.fixture
def as_partner(monkeypatch: pytest.MonkeyPatch, partner_id: int) -> Iterator[Callable[[], None]]:
    def switch() -> None:
        monkeypatch.setenv("DEV_IDENTITY_EMAIL", PARTNER)
        get_settings.cache_clear()

    yield switch
    # The environment is restored after this; the cached settings must not outlive it.
    get_settings.cache_clear()


def _limit(category_ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "spending_limit",
        "name": "Dining under $400",
        "view": "household",
        "category_id": category_ids["Restaurants"],
        "target_amount_cents": 40_000,
    }
    body.update(overrides)
    return body


def _fund(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "emergency_fund",
        "name": "Six months",
        "view": "household",
        "target_months_tenths": 60,
    }
    body.update(overrides)
    return body


def _savings(account_ids: list[int], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "savings_target",
        "name": "House deposit",
        "view": "mine",
        "target_amount_cents": 6_000_000,
        "target_date": "2028-06-30",
        "account_ids": account_ids,
    }
    body.update(overrides)
    return body


# ── each kind, through the API ────────────────────────────────────────────────


def test_each_kind_is_created_and_listed(
    client: TestClient, category_ids: dict[str, int], make_account: Callable[..., int]
) -> None:
    savings = make_account(name="Savings", subtype="savings")

    limit = client.post("/goals", json=_limit(category_ids))
    fund = client.post("/goals", json=_fund())
    target = client.post("/goals", json=_savings([savings]))

    assert [r.status_code for r in (limit, fund, target)] == [201, 201, 201]
    assert limit.json()["category_name"] == "Restaurants"
    assert limit.json()["target_amount_cents"] == 40_000
    assert fund.json()["target_months_tenths"] == 60
    assert target.json()["account_ids"] == [savings]
    assert target.json()["view"] == "mine"
    # Progress is computed on read (ticket 111): here, nothing spent and nothing saved yet.
    assert limit.json()["progress"]["month_to_date_cents"] == 0
    assert target.json()["progress"]["saved_cents"] == 0
    listed = client.get("/goals").json()
    assert [g["name"] for g in listed] == ["House deposit", "Six months", "Dining under $400"]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"kind": "spending_limit", "target_amount_cents": 100}, "needs a category"),
        ({"kind": "emergency_fund"}, "needs a target in months"),
        ({"kind": "savings_target", "target_amount_cents": 100}, "at least one account"),
        ({"kind": "savings_target", "account_ids": [1]}, "needs an amount"),
        ({"kind": "emergency_fund", "target_months_tenths": 60, "target_amount_cents": 1}, None),
        (
            {"kind": "emergency_fund", "target_months_tenths": 60, "account_ids": [1]},
            "Only a savings",
        ),
    ],
)
def test_each_kinds_fields_are_required_and_only_its_own(
    client: TestClient, body: dict[str, Any], detail: str | None
) -> None:
    response = client.post("/goals", json={"name": "x", "view": "household", **body})

    if detail is None:
        # An emergency fund with an amount is allowed at the API: the amount is ignored by
        # nothing and required by nothing, and the database keeps it harmlessly.
        assert response.status_code in {201, 422}
        return
    assert response.status_code == 422
    assert detail in response.json()["detail"]


def test_a_category_on_the_wrong_kind_is_refused(
    client: TestClient, category_ids: dict[str, int]
) -> None:
    response = client.post("/goals", json=_fund(category_id=category_ids["Restaurants"]))

    assert response.status_code == 422
    assert "Only a spending limit has a category" in response.json()["detail"]


def test_a_goal_linked_to_a_closed_account_is_refused(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    closed = make_account(name="Old savings", subtype="savings", closed_at=dt.date(2026, 1, 1))

    response = client.post("/goals", json=_savings([closed]))

    assert response.status_code == 422
    assert "closed account" in response.json()["detail"]


def test_an_unknown_account_or_category_is_refused(
    client: TestClient, category_ids: dict[str, int]
) -> None:
    assert client.post("/goals", json=_savings([999_999])).status_code == 422
    assert client.post("/goals", json=_limit(category_ids, category_id=999_999)).status_code == 422


def test_non_positive_targets_are_refused(client: TestClient, category_ids: dict[str, int]) -> None:
    assert (
        client.post("/goals", json=_limit(category_ids, target_amount_cents=0)).status_code == 422
    )
    assert client.post("/goals", json=_fund(target_months_tenths=0)).status_code == 422


# ── each kind, at the database ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": GoalKind.SPENDING_LIMIT, "target_amount": Decimal("10")},  # no category
        {"kind": GoalKind.EMERGENCY_FUND},  # no months
        {"kind": GoalKind.SAVINGS_TARGET},  # no amount
        {"kind": GoalKind.SAVINGS_TARGET, "target_amount": Decimal("-1")},
        {"kind": GoalKind.EMERGENCY_FUND, "target_months": Decimal("0")},
        {
            "kind": GoalKind.SAVINGS_TARGET,
            "target_amount": Decimal("1"),
            "target_months": Decimal("3"),
        },
    ],
)
def test_the_database_refuses_what_a_kind_does_not_allow(
    db_session: Session, fields: dict[str, Any]
) -> None:
    db_session.add(Goal(name="x", **fields))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_database_refuses_a_category_on_a_non_limit(
    db_session: Session, category_ids: dict[str, int]
) -> None:
    db_session.add(
        Goal(
            name="x",
            kind=GoalKind.EMERGENCY_FUND,
            target_months=Decimal("6"),
            category_id=category_ids["Restaurants"],
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


# ── editing, who sees what, deleting ──────────────────────────────────────────


def test_a_goal_is_edited_in_place_and_archived(
    client: TestClient, category_ids: dict[str, int]
) -> None:
    goal = client.post("/goals", json=_limit(category_ids)).json()

    edited = client.patch(
        f"/goals/{goal['id']}", json={"name": "Dining under $350", "target_amount_cents": 35_000}
    )
    archived = client.patch(f"/goals/{goal['id']}", json={"status": "archived"})

    assert edited.status_code == 200
    assert (edited.json()["name"], edited.json()["target_amount_cents"]) == (
        "Dining under $350",
        35_000,
    )
    assert archived.json()["status"] == "archived"
    assert archived.json()["target_amount_cents"] == 35_000


def test_an_edit_cannot_break_a_kinds_rules(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    savings = make_account(name="Savings", subtype="savings")
    goal = client.post("/goals", json=_savings([savings])).json()

    response = client.patch(f"/goals/{goal['id']}", json={"account_ids": []})

    assert response.status_code == 422


def test_personal_goals_are_their_owners_alone(
    client: TestClient,
    category_ids: dict[str, int],
    make_account: Callable[..., int],
    as_partner: Callable[[], None],
) -> None:
    savings = make_account(name="Savings", subtype="savings")
    mine = client.post("/goals", json=_savings([savings])).json()
    shared = client.post("/goals", json=_limit(category_ids)).json()

    as_partner()

    assert [g["id"] for g in client.get("/goals").json()] == [shared["id"]]
    assert client.patch(f"/goals/{mine['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/goals/{mine['id']}").status_code == 404
    assert client.patch(f"/goals/{shared['id']}", json={"name": "Ours"}).status_code == 200


def test_delete_removes_a_goal_and_its_links(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    savings = make_account(name="Savings", subtype="savings")
    goal = client.post("/goals", json=_savings([savings])).json()

    assert client.delete(f"/goals/{goal['id']}").status_code == 204

    assert client.get("/goals").json() == []
    assert client.get("/export").json()["goal_accounts"] == []


def test_the_export_carries_goals_and_their_accounts(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    savings = make_account(name="Savings", subtype="savings")
    goal = client.post("/goals", json=_savings([savings])).json()

    body = client.get("/export").json()

    assert [(g["id"], g["kind"], g["target_amount"]) for g in body["goals"]] == [
        (goal["id"], "savings_target", "60000.00")
    ]
    assert body["goal_accounts"] == [{"goal_id": goal["id"], "account_id": savings}]


def test_the_demo_cannot_write_goals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, category_ids: dict[str, int]
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        assert client.post("/goals", json=_limit(category_ids)).status_code == 405
        assert client.get("/goals").status_code == 200
    finally:
        get_settings.cache_clear()
