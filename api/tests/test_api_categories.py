"""Tests for the category list.

The list is what every category picker in the app is built from, so the thing worth
asserting is completeness: a picker that silently omits income and transfer categories
cannot express "this was a transfer", which is the correction the transactions screen
exists to make.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_returns_every_seeded_category(client: TestClient) -> None:
    body = client.get("/categories").json()

    names = {row["name"] for row in body}
    assert {"Groceries", "Restaurants", "Salary", "Transfer"} <= names


def test_includes_income_and_transfer_kinds(client: TestClient) -> None:
    """Deriving the list from /spend would return expense categories only.

    A picker built that way cannot express "this was a transfer" or "this was
    income", which are exactly the corrections that keep spend figures honest.
    """
    body = client.get("/categories").json()

    assert {row["kind"] for row in body} == {"income", "expense", "transfer"}


def test_reports_the_parent_link(client: TestClient) -> None:
    body = {row["name"]: row for row in client.get("/categories").json()}

    assert body["Groceries"]["parent_id"] == body["Food"]["id"]
    assert body["Food"]["parent_id"] is None


def test_parents_come_before_their_children(client: TestClient) -> None:
    """So a grouped picker can be built by walking the list once."""
    body = client.get("/categories").json()

    seen: set[int] = set()
    for row in body:
        if row["parent_id"] is not None:
            assert row["parent_id"] in seen, f"{row['name']} came before its parent"
        seen.add(row["id"])


def test_children_are_alphabetical_within_a_parent(client: TestClient) -> None:
    body = client.get("/categories").json()
    food_id = next(row["id"] for row in body if row["name"] == "Food")

    children = [row["name"] for row in body if row["parent_id"] == food_id]
    assert children == sorted(children)
