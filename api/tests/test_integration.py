"""End-to-end paths through the real database.

The unit and functional tests each check one service or one route. These check that
the pieces meet: seed, import, categorise, and read a figure back out. That join is
what the three parallel lanes could not test individually, and it is where a
disagreement between two correct halves would show up.

Every test here runs against migrated Postgres through the app's own HTTP surface —
no service functions called directly, because "the API returns the right number" is
the claim, not "the service does".
"""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import app

# ── completeness ──────────────────────────────────────────────────────────────


def test_no_route_answers_501(client: TestClient) -> None:
    """The completeness check for the whole contract-first approach.

    Ticket 012 declared every route and stubbed it at 501 so three lanes could build
    against one generated contract. This proves each lane actually filled its share —
    it is the cheapest possible guard against a route everyone assumed the other lane
    had built.

    Bodies are deliberately empty and ids deliberately absent: a 422 or a 404 means the
    route is real and disagreed with the request, which is all this asserts. Only 501
    fails.
    """
    from tests.test_contract import _api_routes

    unimplemented: list[str] = []
    for route in _api_routes():
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            path = (
                route.path.replace("{account_id}", "1")
                .replace("{rule_id}", "1")
                .replace("{transaction_id}", "1")
            )
            response = client.request(method, path, json={} if method != "GET" else None)
            if response.status_code == 501:
                unimplemented.append(f"{method} {route.path}")

    assert not unimplemented, f"still stubbed: {sorted(unimplemented)}"


# ── the pipeline ──────────────────────────────────────────────────────────────

CSV = """Date,Description,Amount
2026-03-04,CORNER MARKET,-52.30
2026-03-11,CORNER MARKET,-18.75
2026-03-18,PETROL PLUS,-61.00
"""


def _import(client: TestClient, account_id: int, content: str = CSV) -> dict[str, Any]:
    preview = client.post(
        "/import/csv/preview",
        data={"account_id": str(account_id)},
        files={"file": ("export.csv", io.BytesIO(content.encode()), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()

    commit = client.post(
        "/import/csv/commit",
        json={
            "account_id": account_id,
            "content": content,
            "mapping": body["detected_mapping"],
        },
    )
    assert commit.status_code == 200, commit.text
    result: dict[str, Any] = commit.json()
    return result


def test_import_then_categorise_then_read_the_spend_back(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """The whole loop, through HTTP, against a real database."""
    account_id = make_account("Checking")
    categories = {
        name: cid for name, cid in db_session.execute(text("SELECT name, id FROM categories")).all()
    }

    result = _import(client, account_id)
    assert result["created"] == 3

    rule = client.post(
        "/rules",
        json={"pattern": "CORNER MARKET", "category_id": categories["Groceries"]},
    )
    assert rule.status_code == 201, rule.text

    applied = client.post("/rules/apply", json={}).json()
    assert applied["categorised"] == 2

    spend = client.get("/spend", params={"from": "2026-03-01", "to": "2026-03-31"}).json()
    buckets = {b["category_name"]: b["spend_cents"] for b in spend["buckets"]}

    # $52.30 + $18.75, as cents, having crossed the parser, the planner, the upsert,
    # the rules engine and the rollup.
    assert buckets["Groceries"] == 7_105
    assert buckets["Uncategorised"] == 6_100


def test_reimporting_the_same_file_changes_nothing(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    """021's idempotency claim, verified after a full round trip rather than in isolation."""
    account_id = make_account("Checking")
    _import(client, account_id)

    second = _import(client, account_id)

    assert (second["created"], second["updated"]) == (0, 0)
    assert second["skipped"] == 3


def test_a_manual_category_survives_a_rules_rerun(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """The guarantee `category_source` exists for, end to end.

    Ticket 009 designed the column, 022 implemented the protection, and 023 was the
    first thing that could write `manual`. This is the only test that exercises all
    three together: categorise through HTTP, run every rule over all history, and
    check the human's decision is still there.
    """
    account_id = make_account("Checking")
    categories = {
        name: cid for name, cid in db_session.execute(text("SELECT name, id FROM categories")).all()
    }
    _import(client, account_id)

    rows = client.get("/transactions").json()["items"]
    corner = next(row for row in rows if row["merchant"] == "CORNER MARKET")

    # A human disagrees with what any rule would say.
    client.patch(f"/transactions/{corner['id']}", json={"category_id": categories["Restaurants"]})
    client.post("/rules", json={"pattern": "CORNER MARKET", "category_id": categories["Groceries"]})

    applied = client.post("/rules/apply", json={}).json()

    after = {row["id"]: row for row in client.get("/transactions").json()["items"]}
    assert after[corner["id"]]["category"]["name"] == "Restaurants"
    assert after[corner["id"]]["category_source"] == "manual"
    assert applied["manual_preserved"] >= 1


def test_a_balance_write_moves_net_worth(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    """Records a balance over HTTP and reads the aggregate back.

    This is the path that shipped broken: every write endpoint answered 200 and
    persisted nothing, and no functional test could see it because they all shared a
    rolled-back session with the app. Reading the figure back through a *different*
    request is what catches it.
    """
    account_id = make_account("Savings")
    today = dt.date.today()

    client.post(
        f"/accounts/{account_id}/stakes",
        json={
            "owner_user_id": client.get("/auth/session").json()["user_id"],
            "percentage_bps": 10_000,
            "effective_from": today.isoformat(),
        },
    )
    recorded = client.post(
        f"/accounts/{account_id}/balances",
        json={"as_of": today.isoformat(), "balance_cents": 250_000},
    )
    assert recorded.status_code in (200, 201), recorded.text

    net = client.get("/net-worth").json()

    assert net["assets_cents"] >= 250_000


def test_transfers_stay_out_of_spend_after_a_real_import(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """The claim the whole spend surface rests on, verified through the import path."""
    account_id = make_account("Checking")
    categories = {
        name: cid for name, cid in db_session.execute(text("SELECT name, id FROM categories")).all()
    }
    content = (
        "Date,Description,Amount\n"
        "2026-03-04,CORNER MARKET,-52.30\n"
        "2026-03-05,TRANSFER TO BROKERAGE,-2000.00\n"
    )
    _import(client, account_id, content)

    client.post(
        "/rules",
        json={
            "pattern": "TRANSFER TO",
            "category_id": categories["Investment Contribution"],
        },
    )
    client.post("/rules/apply", json={})

    spend = client.get("/spend", params={"from": "2026-03-01", "to": "2026-03-31"}).json()

    # $2,000 moved to a brokerage is not $2,000 of spending.
    assert spend["total_cents"] == 5_230
    assert spend["excluded_transfer_count"] == 1


def test_the_openapi_surface_matches_what_the_app_serves(client: TestClient) -> None:
    """A generated client is only worth anything if the server agrees with it."""
    served = client.get("/openapi.json").json()

    assert set(served["paths"]) == set(app.openapi()["paths"])
