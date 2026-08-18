"""Tests for the transactions API and the manual category override.

The round-trip test is the one that matters: categorise by hand, re-run every rule
over all history, and assert the human's decision survived. Until this ticket nothing
in the codebase wrote `'manual'`, so 022's protection had nothing to protect.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

JAN = dt.date(2026, 1, 15)


# ── the override, and what it protects against ────────────────────────────────


def test_setting_a_category_records_it_as_manual(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-40.00", merchant="AMBIGUOUS")

    body = client.patch(
        f"/transactions/{transaction_id}", json={"category_id": category_ids["Shopping"]}
    ).json()

    assert body["category"]["name"] == "Shopping"
    assert body["category_source"] == "manual"


def test_a_manual_category_survives_a_full_rule_run(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """End to end through HTTP, which is how it will actually happen.

    A rule says Groceries. A person says Shopping. Re-running every rule over all
    history must not undo the person.
    """
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-40.00", merchant="AMBIGUOUS VENDOR")
    client.post("/rules", json={"pattern": "AMBIGUOUS", "category_id": category_ids["Groceries"]})

    client.patch(f"/transactions/{transaction_id}", json={"category_id": category_ids["Shopping"]})
    applied = client.post("/rules/apply", json={"only_uncategorised": False}).json()

    after = client.get("/transactions").json()["items"][0]
    assert after["category"]["name"] == "Shopping"
    assert after["category_source"] == "manual"
    assert applied["manual_preserved"] == 1


def test_clearing_a_category_clears_its_provenance(
    client: TestClient,
    db_session: Session,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """An uncategorised row still marked 'manual' would be invisible to rules for ever."""
    account_id = make_account()
    transaction_id = make_transaction(
        account_id,
        JAN,
        "-40.00",
        category_id=category_ids["Shopping"],
        category_source="manual",
    )

    client.patch(f"/transactions/{transaction_id}", json={"category_id": None})

    source = db_session.execute(
        text("SELECT category_source FROM transactions WHERE id = :i"), {"i": transaction_id}
    ).scalar_one()
    assert source is None


def test_bulk_categorise_also_writes_manual(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    ids = [make_transaction(account_id, JAN, "-10.00", merchant=f"M{i}") for i in range(3)]

    body = client.post(
        "/transactions/bulk-categorise",
        json={"transaction_ids": ids, "category_id": category_ids["Groceries"]},
    ).json()

    assert body["updated"] == 3
    for item in client.get("/transactions").json()["items"]:
        assert item["category_source"] == "manual"


# ── listing and filters ───────────────────────────────────────────────────────


def test_newest_first(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    account_id = make_account()
    make_transaction(account_id, dt.date(2026, 1, 1), "-10.00", merchant="OLD")
    make_transaction(account_id, dt.date(2026, 6, 1), "-10.00", merchant="NEW")

    items = client.get("/transactions").json()["items"]

    assert [i["merchant"] for i in items] == ["NEW", "OLD"]


def test_filter_by_date_range(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    account_id = make_account()
    make_transaction(account_id, dt.date(2026, 1, 1), "-10.00", merchant="JAN")
    make_transaction(account_id, dt.date(2026, 6, 1), "-10.00", merchant="JUN")

    items = client.get("/transactions", params={"from": "2026-05-01", "to": "2026-07-01"}).json()[
        "items"
    ]

    assert [i["merchant"] for i in items] == ["JUN"]


def test_filter_to_uncategorised(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """The filter the dashboard's uncategorised prompt links to."""
    account_id = make_account()
    make_transaction(
        account_id, JAN, "-10.00", merchant="KNOWN", category_id=category_ids["Groceries"]
    )
    make_transaction(account_id, JAN, "-20.00", merchant="MYSTERY")

    items = client.get("/transactions", params={"uncategorised": True}).json()["items"]

    assert [i["merchant"] for i in items] == ["MYSTERY"]


def test_search_matches_merchant_case_insensitively(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    account_id = make_account()
    make_transaction(account_id, JAN, "-10.00", merchant="BLUEBIRD COFFEE")
    make_transaction(account_id, JAN, "-20.00", merchant="GREENLEAF")

    items = client.get("/transactions", params={"search": "bluebird"}).json()["items"]

    assert len(items) == 1


def test_filter_by_account(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    first = make_account(name="A")
    second = make_account(name="B")
    make_transaction(first, JAN, "-10.00", merchant="ON A")
    make_transaction(second, JAN, "-20.00", merchant="ON B")

    items = client.get("/transactions", params={"account_id": second}).json()["items"]

    assert [i["merchant"] for i in items] == ["ON B"]


def test_pagination_reports_the_full_total(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    """The total is of matching rows, not of the page — the UI needs it for paging."""
    account_id = make_account()
    for i in range(5):
        make_transaction(account_id, JAN, "-10.00", merchant=f"M{i}")

    body = client.get("/transactions", params={"limit": 2, "offset": 0}).json()

    assert len(body["items"]) == 2
    assert body["page"]["total"] == 5


def test_amounts_are_signed_cents(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    account_id = make_account()
    make_transaction(account_id, JAN, "-42.50", merchant="OUT")

    assert client.get("/transactions").json()["items"][0]["amount_cents"] == -4250


def test_account_name_comes_along(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    """So a transactions table does not need one lookup per row."""
    account_id = make_account(name="Everyday checking")
    make_transaction(account_id, JAN, "-10.00")

    assert client.get("/transactions").json()["items"][0]["account_name"] == "Everyday checking"


# ── errors ────────────────────────────────────────────────────────────────────


def test_unknown_transaction_is_a_404(client: TestClient) -> None:
    assert client.patch("/transactions/999999", json={"category_id": None}).status_code == 404


def test_unknown_category_is_a_404_not_a_500(
    client: TestClient, make_account: Callable[..., int], make_transaction: Callable[..., int]
) -> None:
    account_id = make_account()
    transaction_id = make_transaction(account_id, JAN, "-10.00")

    response = client.patch(f"/transactions/{transaction_id}", json={"category_id": 999999})

    assert response.status_code == 404


def test_rejects_an_over_large_page(client: TestClient) -> None:
    assert client.get("/transactions", params={"limit": 5000}).status_code == 422


def test_filter_to_categorised_only(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    """`uncategorised=false` is the inverse, not "no filter"."""
    account_id = make_account()
    make_transaction(
        account_id, JAN, "-10.00", merchant="KNOWN", category_id=category_ids["Groceries"]
    )
    make_transaction(account_id, JAN, "-20.00", merchant="MYSTERY")

    items = client.get("/transactions", params={"uncategorised": False}).json()["items"]

    assert [i["merchant"] for i in items] == ["KNOWN"]


def test_filter_by_category(
    client: TestClient,
    make_account: Callable[..., int],
    make_transaction: Callable[..., int],
    category_ids: dict[str, int],
) -> None:
    account_id = make_account()
    make_transaction(
        account_id, JAN, "-10.00", merchant="FOOD", category_id=category_ids["Groceries"]
    )
    make_transaction(account_id, JAN, "-20.00", merchant="FUEL", category_id=category_ids["Fuel"])

    items = client.get("/transactions", params={"category_id": category_ids["Fuel"]}).json()[
        "items"
    ]

    assert [i["merchant"] for i in items] == ["FUEL"]
