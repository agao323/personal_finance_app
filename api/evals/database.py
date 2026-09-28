"""The eval database: `pfa_eval` on the local Postgres, created and migrated on demand.

The eval world is built here, never in the development database: `make eval` rebuilds it for
every run, and `make eval-fixtures` borrows it inside a transaction it rolls back. Either way the
owner's own development data is not touched.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DEFAULT_EVAL_DB = "postgresql+psycopg://pfa:pfa_local_dev@localhost:5432/pfa_eval"


def url() -> str:
    return os.environ.get("EVAL_DATABASE_URL", DEFAULT_EVAL_DB)


def ensure(database_url: str) -> None:
    """Create the database if it is missing, and migrate it to head."""
    from alembic.config import Config

    from alembic import command

    target = make_url(database_url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": target.database}
        ).first()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()

    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    command.upgrade(config, "head")
