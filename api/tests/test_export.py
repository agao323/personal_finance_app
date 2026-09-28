"""The full export, and the guard that keeps it full.

`GET /export` is layer two of the backup story since ADR 0008, so "is every table in here"
stopped being a nicety and became the thing the file is for.

It was a hand-maintained selection and the selection went stale: `institutions`,
`card_perks`, `perk_redemptions` and `import_mappings` were all missing, for a year, while
the ticket claimed "the full dataset". The first test below is the one that would have
caught it.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import Base
from app.routers.export import EXPORTED
from app.schemas.export import ExportRead
from scripts.restore_local import _coerced, _ordered, insert_order


def test_every_mapped_table_is_exported() -> None:
    """The guard. A new table cannot silently fall out of the backup.

    Compared against `Base.metadata`, which is the same thing Alembic autogenerates from,
    so a table that exists in the database is a table this notices.
    """
    mapped = set(Base.metadata.tables)

    assert mapped - set(EXPORTED) == set(), "table(s) missing from the export"


def test_every_exported_table_has_a_field_to_land_in() -> None:
    """The other direction: a name in `EXPORTED` with nowhere to go is a 500 at runtime."""
    fields = set(ExportRead.model_fields) - {"meta"}

    assert set(EXPORTED) == fields


def test_the_export_carries_cards_and_their_recorded_uses(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    """The four tables that were missing, asserted by name rather than by count."""
    account_id = make_account(name="Sapphire", kind="liability", subtype="credit_card")
    perk = client.post(
        f"/cards/{account_id}/perks",
        json={
            "name": "Dining credit",
            "value_cents": 2_500,
            "cadence": "monthly",
            "anchor_on": "2026-01-01",
        },
    ).json()
    client.post(f"/perks/{perk['id']}/redemptions", json={"on": "2026-06-15"})

    body = client.get("/export").json()

    assert [p["name"] for p in body["card_perks"]] == ["Dining credit"]
    assert len(body["perk_redemptions"]) == 1
    assert body["perk_redemptions"][0]["period_start"] == "2026-06-01"
    # The account's institution comes too. Without it the export names an issuer by an id
    # that resolves to nothing.
    assert len(body["institutions"]) == 1
    # Present even when empty: a missing key and an empty table are different facts.
    assert body["import_mappings"] == []


def test_money_crosses_as_a_string_not_a_float(
    client: TestClient, db_session: Session, make_account: Callable[..., int]
) -> None:
    """The export is what someone rebuilds from. A float would round the balances it exists
    to preserve, quietly, and only for the values where it matters."""
    account_id = make_account(name="Brokerage", kind="liquid_asset", subtype="brokerage")
    db_session.execute(
        text(
            "INSERT INTO balance_snapshots (account_id, as_of, balance, source) "
            "VALUES (:a, '2026-06-01', :b, 'manual')"
        ),
        {"a": account_id, "b": Decimal("12345.67")},
    )
    db_session.flush()

    body = client.get("/export").json()

    balances = [row["balance"] for row in body["balance_snapshots"]]
    assert balances == ["12345.67"]
    assert all(isinstance(value, str) for value in balances)


def test_the_meta_counts_match_the_rows(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    make_account(name="Chequing", kind="liquid_asset", subtype="checking")

    body = client.get("/export").json()

    assert body["meta"]["account_count"] == len(body["accounts"])
    assert body["meta"]["snapshot_count"] == len(body["balance_snapshots"])
    assert body["meta"]["transaction_count"] == len(body["transactions"])


# ── restoring what the export wrote ───────────────────────────────────────────


def test_restore_inserts_parents_before_children() -> None:
    """The bug the first restore drill found, as a test.

    The restore originally walked `EXPORTED`, which is the response contract's field order.
    It puts `ownership_stakes` before `users`, and the foreign key refused. The order now
    comes from the schema's own dependency graph.
    """
    names = [table.name for table in insert_order()]

    assert names.index("users") < names.index("ownership_stakes")
    assert names.index("accounts") < names.index("balance_snapshots")
    assert names.index("categories") < names.index("transactions")
    assert names.index("card_perks") < names.index("perk_redemptions")


def test_every_exported_table_is_in_the_insert_order() -> None:
    """A table that is exported but never inserted restores as silently empty."""
    assert {table.name for table in insert_order()} == set(EXPORTED)


def test_a_self_referencing_table_puts_roots_first() -> None:
    """`categories` points at itself through `parent_id`, and table ordering cannot help:
    the rows inside one insert have to be ordered too."""
    categories = Base.metadata.tables["categories"]
    rows = [
        {"id": 2, "name": "Groceries", "parent_id": 1},
        {"id": 1, "name": "Food", "parent_id": None},
    ]

    assert [row["id"] for row in _ordered(categories, rows)] == [1, 2]


def test_ordering_leaves_a_table_without_a_self_reference_alone() -> None:
    accounts = Base.metadata.tables["accounts"]
    rows = [{"id": 2}, {"id": 1}]

    assert _ordered(accounts, rows) == rows


def test_uuids_come_back_as_uuids() -> None:
    """The export writes a uuid as a string; restore must not hand the string to the driver."""
    import uuid

    table = Base.metadata.tables["advisor_conversations"]
    value = "00000000-0000-4000-8000-000000000001"

    (row,) = _coerced(table, [{"id": value, "title_text": "x", "view": "mine"}])

    assert row["id"] == uuid.UUID(value)
    assert row["title_text"] == "x"
