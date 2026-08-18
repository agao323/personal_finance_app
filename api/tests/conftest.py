"""Test fixtures.

The suite runs against a real Postgres — the same engine production uses — rather
than SQLite. Ownership and money queries lean on Postgres semantics (``NUMERIC``,
date ranges, ``ON CONFLICT``), and a SQLite stand-in would pass tests that production
fails.

``make test-api`` starts the compose ``postgres`` service first, so a clean clone
needs nothing installed beyond Docker.
"""

import datetime as dt
import os
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.config import get_settings
from app.db import get_engine, get_session, get_sessionmaker
from app.main import app

API_ROOT = Path(__file__).resolve().parent.parent


def _alembic_upgrade(url: str) -> None:
    """Run `alembic upgrade head` against `url`."""
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    # env.py reads this in preference to Settings.
    os.environ["ALEMBIC_DATABASE_URL"] = url
    command.upgrade(config, "head")


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pfa:pfa_local_dev@localhost:5432/pfa_test",
)


@pytest.fixture(scope="session", autouse=True)
def _point_app_at_the_test_database() -> Iterator[None]:
    """Make the application's own settings resolve to the test database.

    Without this, ``/ready`` would open a connection against whatever ``DATABASE_URL``
    the developer happens to have exported — or fail outright, since pytest runs from
    ``api/`` and the compose ``.env`` lives at the repo root. Either way the test would
    be measuring the wrong database.
    """
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    yield

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Create a throwaway database for the session and drop it afterwards."""
    url = make_url(TEST_DATABASE_URL)
    database = url.database
    assert database, "TEST_DATABASE_URL must name a database"

    # Connect to the maintenance database to create the test one. CREATE DATABASE
    # cannot run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{database}"'))

    # Migrations, never metadata.create_all(). Building the schema a second way means
    # the tests pass against a schema production never has, and a broken migration
    # ships green. This is also the only thing that exercises the migration on every
    # run.
    _alembic_upgrade(TEST_DATABASE_URL)

    test_engine = create_engine(TEST_DATABASE_URL)

    yield test_engine

    test_engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session whose writes are rolled back when the test ends.

    The session joins an outer transaction on a dedicated connection, so committing
    inside a test creates a savepoint rather than persisting. Keeps the suite fast —
    no schema rebuild between tests — and keeps tests independent.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """A TestClient whose request-scoped sessions are the rolled-back test session."""

    def override_get_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def owner_id(db_session: Session) -> int:
    """The user seeded by the initial migration."""
    return int(db_session.execute(text("SELECT id FROM users LIMIT 1")).scalar_one())


@pytest.fixture
def partner_id(db_session: Session) -> int:
    """A second household member, for the stake-splitting cases."""
    return int(
        db_session.execute(
            text(
                "INSERT INTO users (email, display_name, is_active) "
                "VALUES ('partner@example.invalid', 'Partner', true) RETURNING id"
            )
        ).scalar_one()
    )


@pytest.fixture
def make_account(db_session: Session) -> Callable[..., int]:
    """Create an account and return its id.

    Deliberately does *not* create an ownership stake — the tests for
    `create_initial_stake` need an account without one, and a fixture that quietly
    added a row would make those tests assert the wrong thing.
    """

    def _make(
        name: str = "Checking",
        kind: str = "liquid_asset",
        subtype: str = "checking",
        closed_at: dt.date | None = None,
    ) -> int:
        institution_id = db_session.execute(
            text("INSERT INTO institutions (name) VALUES (:n) RETURNING id"),
            {"n": f"Institution {name}"},
        ).scalar_one()
        return int(
            db_session.execute(
                text(
                    "INSERT INTO accounts "
                    "(institution_id, name, kind, subtype, source, currency, closed_at) "
                    "VALUES (:i, :n, :k, :s, 'manual', 'USD', :c) RETURNING id"
                ),
                {"i": institution_id, "n": name, "k": kind, "s": subtype, "c": closed_at},
            ).scalar_one()
        )

    return _make


@pytest.fixture
def category_ids(db_session: Session) -> dict[str, int]:
    """Seeded category ids by name, for tests that need to categorise something."""
    return {
        name: cid for name, cid in db_session.execute(text("SELECT name, id FROM categories")).all()
    }


@pytest.fixture
def make_transaction(db_session: Session) -> Callable[..., int]:
    """Insert a transaction. Outflows are negative, matching the wire convention."""

    def _make(
        account_id: int,
        posted_at: dt.date,
        amount: str,
        merchant: str = "Test Merchant",
        category_id: int | None = None,
        external_id: str | None = None,
        category_source: str | None = None,
    ) -> int:
        return int(
            db_session.execute(
                text(
                    "INSERT INTO transactions "
                    "(account_id, posted_at, amount, merchant, category_id, "
                    " external_id, category_source) "
                    "VALUES (:a, :d, :amt, :m, :c, :e, :cs) RETURNING id"
                ),
                {
                    "a": account_id,
                    "d": posted_at,
                    "amt": Decimal(amount),
                    "m": merchant,
                    "c": category_id,
                    "e": external_id,
                    "cs": category_source,
                },
            ).scalar_one()
        )

    return _make
