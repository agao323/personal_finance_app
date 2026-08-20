"""Schema tests: constraints, enums, seed data, and the migration round trip.

These assert what the *database* enforces, not what the models declare. A CHECK
constraint that exists in a model but never made it into the migration is exactly the
kind of gap that only shows up in production.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import Engine, Numeric, create_engine, inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import TEST_DATABASE_URL, _alembic_upgrade

EXPECTED_TABLES = {
    "users",
    "institutions",
    "accounts",
    "ownership_stakes",
    "balance_snapshots",
    "categories",
    "transactions",
    "categorization_rules",
    "import_mappings",
    "data_marker",
}


# ── structure ─────────────────────────────────────────────────────────────────


def test_every_v1_table_exists(engine: Engine) -> None:
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_money_columns_are_numeric_19_2(engine: Engine) -> None:
    """The one bug class that silently corrupts financial data."""
    inspector = inspect(engine)
    money = [
        ("balance_snapshots", "balance"),
        ("transactions", "amount"),
    ]
    for table, column in money:
        col = next(c for c in inspector.get_columns(table) if c["name"] == column)
        # Inspector returns TypeEngine; NUMERIC carries precision/scale.
        numeric = cast("Numeric[Decimal]", col["type"])
        assert numeric.precision == 19, f"{table}.{column}"
        assert numeric.scale == 2, f"{table}.{column}"


def test_no_floating_point_column_anywhere(engine: Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND data_type IN ('real', 'double precision')"
            )
        ).all()
    assert rows == []


# ── enums ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("enum_name", "expected"),
    [
        ("account_kind", {"liquid_asset", "illiquid_asset", "liability"}),
        ("data_source", {"manual", "csv", "teller", "plaid", "simplefin"}),
        ("category_kind", {"income", "expense", "transfer"}),
        ("category_source", {"import", "rule", "manual"}),
        ("match_type", {"contains", "equals", "starts_with", "regex"}),
    ],
)
def test_enum_labels_are_values_not_python_names(
    engine: Engine, enum_name: str, expected: set[str]
) -> None:
    """Labels must be `liquid_asset`, never `LIQUID_ASSET`.

    SQLAlchemy stores `.name` by default, which would put the Python member name in
    the database while every JSON payload and CSV says the value. The mismatch is
    invisible until something compares the two.
    """
    with engine.connect() as connection:
        labels = set(
            connection.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :name"
                ),
                {"name": enum_name},
            ).scalars()
        )
    assert labels == expected


def test_source_enum_ships_connectors_not_yet_implemented(engine: Engine) -> None:
    """So adding a connector later is code, not a migration."""
    with engine.connect() as connection:
        labels = set(
            connection.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'data_source'"
                )
            ).scalars()
        )
    assert {"teller", "plaid", "simplefin"} <= labels


# ── constraints ───────────────────────────────────────────────────────────────


def _institution(session: Session) -> int:
    row = session.execute(
        text("INSERT INTO institutions (name) VALUES ('Test Bank') RETURNING id")
    ).one()
    return int(row[0])


def _account(session: Session, currency: str = "USD") -> int:
    row = session.execute(
        text(
            "INSERT INTO accounts (institution_id, name, kind, subtype, source, currency) "
            "VALUES (:inst, 'Checking', 'liquid_asset', 'checking', 'manual', :currency) "
            "RETURNING id"
        ),
        {"inst": _institution(session), "currency": currency},
    ).one()
    return int(row[0])


def test_currency_must_be_usd(db_session: Session) -> None:
    """v1 is single-currency. Mixed currencies would sum silently."""
    with pytest.raises((IntegrityError, DataError)):
        _account(db_session, currency="EUR")


def test_stake_percentage_must_be_in_range(db_session: Session) -> None:
    account_id = _account(db_session)
    user_id = int(db_session.execute(text("SELECT id FROM users LIMIT 1")).scalar_one())

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ownership_stakes "
                "(account_id, owner_user_id, percentage, effective_from) "
                "VALUES (:a, :u, 150.00, '2026-01-01')"
            ),
            {"a": account_id, "u": user_id},
        )


def test_stake_effective_to_must_follow_effective_from(db_session: Session) -> None:
    account_id = _account(db_session)
    user_id = int(db_session.execute(text("SELECT id FROM users LIMIT 1")).scalar_one())

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ownership_stakes "
                "(account_id, owner_user_id, percentage, effective_from, effective_to) "
                "VALUES (:a, :u, 50.00, '2026-06-01', '2026-01-01')"
            ),
            {"a": account_id, "u": user_id},
        )


def test_one_snapshot_per_account_per_date(db_session: Session) -> None:
    account_id = _account(db_session)
    insert = text(
        "INSERT INTO balance_snapshots (account_id, as_of, balance, source) "
        "VALUES (:a, :d, :b, 'manual')"
    )
    db_session.execute(insert, {"a": account_id, "d": dt.date(2026, 1, 1), "b": Decimal("100.00")})

    with pytest.raises(IntegrityError):
        db_session.execute(
            insert, {"a": account_id, "d": dt.date(2026, 1, 1), "b": Decimal("200.00")}
        )


def test_external_id_is_unique_per_account(db_session: Session) -> None:
    """Ingestion is upsert, never insert — the idempotency key is a constraint."""
    account_id = _account(db_session)
    insert = text(
        "INSERT INTO transactions (account_id, external_id, posted_at, amount) "
        "VALUES (:a, 'ext-1', '2026-01-01', -12.34)"
    )
    db_session.execute(insert, {"a": account_id})

    with pytest.raises(IntegrityError):
        db_session.execute(insert, {"a": account_id})


def test_manual_transactions_without_external_id_are_not_constrained(
    db_session: Session,
) -> None:
    """The unique index is partial: NULL external ids may repeat freely."""
    account_id = _account(db_session)
    insert = text(
        "INSERT INTO transactions (account_id, external_id, posted_at, amount) "
        "VALUES (:a, NULL, '2026-01-01', -12.34)"
    )
    db_session.execute(insert, {"a": account_id})
    db_session.execute(insert, {"a": account_id})

    count = db_session.execute(
        text("SELECT count(*) FROM transactions WHERE account_id = :a"), {"a": account_id}
    ).scalar_one()
    assert count == 2


def test_balance_keeps_two_decimal_places(db_session: Session) -> None:
    account_id = _account(db_session)
    db_session.execute(
        text(
            "INSERT INTO balance_snapshots (account_id, as_of, balance, source) "
            "VALUES (:a, '2026-02-01', 1234.567, 'manual')"
        ),
        {"a": account_id},
    )
    stored = db_session.execute(
        text("SELECT balance FROM balance_snapshots WHERE account_id = :a"), {"a": account_id}
    ).scalar_one()
    # Rounded by the column, and exact — not 1234.56999999.
    assert stored == Decimal("1234.57")


# ── seed ──────────────────────────────────────────────────────────────────────


def test_seeds_one_owner(db_session: Session) -> None:
    assert db_session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1


def test_seeds_a_synthetic_data_marker(db_session: Session) -> None:
    """Defaults to synthetic. Production flips it after first deploy."""
    is_real = db_session.execute(text("SELECT is_real FROM data_marker")).scalar_one()
    assert is_real is False


def test_seeds_categories_of_every_kind(db_session: Session) -> None:
    kinds = set(db_session.execute(text("SELECT DISTINCT kind FROM categories")).scalars())
    assert kinds == {"income", "expense", "transfer"}


def test_seeded_taxonomy_is_two_levels_deep(db_session: Session) -> None:
    """A child of a child would break every parent-category rollup."""
    depth_three = db_session.execute(
        text(
            "SELECT count(*) FROM categories c "
            "JOIN categories p ON c.parent_id = p.id "
            "WHERE p.parent_id IS NOT NULL"
        )
    ).scalar_one()
    assert depth_three == 0


def test_seeds_a_transfer_category(db_session: Session) -> None:
    """Spend rollups filter on this; without it every total is wrong."""
    count = db_session.execute(
        text("SELECT count(*) FROM categories WHERE kind = 'transfer'")
    ).scalar_one()
    assert count >= 1


# ── migration round trip ──────────────────────────────────────────────────────


def test_upgrade_downgrade_upgrade_is_clean() -> None:
    """Runs against its own database so it cannot disturb the session fixture.

    The failure this catches is real and was hit while writing the migration: Postgres
    keeps an enum type after its table is dropped, so a downgrade that does not drop
    the types makes the next upgrade fail with "type already exists".
    """
    from alembic.config import Config

    from alembic import command
    from tests.conftest import API_ROOT

    url = TEST_DATABASE_URL.replace("/pfa_test", "/pfa_roundtrip")
    admin = create_engine(
        TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text('DROP DATABASE IF EXISTS "pfa_roundtrip" WITH (FORCE)'))
        connection.execute(text('CREATE DATABASE "pfa_roundtrip"'))

    try:
        config = Config(str(API_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(API_ROOT / "alembic"))
        import os

        os.environ["ALEMBIC_DATABASE_URL"] = url

        command.upgrade(config, "head")
        command.downgrade(config, "base")

        # No enum type may survive the downgrade.
        engine = create_engine(url)
        with engine.connect() as connection:
            leftover = connection.execute(
                text("SELECT typname FROM pg_type WHERE typtype = 'e'")
            ).scalars()
            assert list(leftover) == []
        engine.dispose()

        command.upgrade(config, "head")
    finally:
        os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE IF EXISTS "pfa_roundtrip" WITH (FORCE)'))
        admin.dispose()


# `_alembic_upgrade` is imported so the fixture's helper stays covered by name here.
assert callable(_alembic_upgrade)
