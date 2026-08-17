"""Database engine, session factory, and the declarative base.

The engine is built lazily rather than at import time so that importing ``app.db``
never requires a reachable database — which is what lets ``/health`` stay honest and
lets tests import the app without Postgres running.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all models. Ticket 009 defines the schema against it."""


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine.

    Pool settings target Neon's pooled endpoint, which puts PgBouncer in transaction
    mode in front of Postgres:

    - ``prepare_threshold=None`` disables psycopg's implicit prepared statements.
      Transaction-mode pooling hands each transaction a different backend, so a
      statement prepared on one is not available on the next.
    - ``pool_pre_ping`` discards connections that died while the compute was
      autosuspended, instead of surfacing the first query after an idle period as an
      error.
    - The pool stays small because PgBouncer is already doing the pooling, and this
      app serves one household.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    with get_sessionmaker()() as session:
        yield session
