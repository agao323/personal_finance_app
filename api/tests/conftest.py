"""Test fixtures.

The suite runs against a real Postgres — the same engine production uses — rather
than SQLite. Ownership and money queries lean on Postgres semantics (``NUMERIC``,
date ranges, ``ON CONFLICT``), and a SQLite stand-in would pass tests that production
fails.

``make test-api`` starts the compose ``postgres`` service first, so a clean clone
needs nothing installed beyond Docker.
"""

import os
from collections.abc import Iterator
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
