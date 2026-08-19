"""Tests for the request-scoped session.

These exist because the rest of the suite structurally cannot catch what they cover.
`conftest.py` overrides `get_session` with a session joined to an outer transaction
that is rolled back after each test, so within a test a `flush` is indistinguishable
from a `commit` — every write endpoint's functional test passed while the write
surface persisted nothing at all.

So these use the real dependency and verify persistence from a *different* session.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.db import get_session

PROBE = "Commit Probe Institution"


def _count(engine: Engine, name: str) -> int:
    with Session(bind=engine) as session:
        return int(
            session.execute(
                text("SELECT count(*) FROM institutions WHERE name = :n"), {"n": name}
            ).scalar_one()
        )


@pytest.fixture
def cleanup(engine: Engine) -> Iterator[None]:
    """Remove the probe row afterwards — these tests really do write."""
    yield
    with Session(bind=engine) as session:
        session.execute(text("DELETE FROM institutions WHERE name LIKE :n"), {"n": f"{PROBE}%"})
        session.commit()


def test_a_completed_request_commits(engine: Engine, cleanup: None) -> None:
    """Endpoints flush; the dependency is what makes the write durable."""
    generator = get_session()
    session = next(generator)
    session.execute(text("INSERT INTO institutions (name) VALUES (:n)"), {"n": PROBE})

    # Exhausting the generator is what FastAPI does after the handler returns.
    with pytest.raises(StopIteration):
        next(generator)

    assert _count(engine, PROBE) == 1


def test_a_failed_request_rolls_back(engine: Engine, cleanup: None) -> None:
    """A handler that raises after a partial write must leave nothing behind.

    This covers HTTPException too: a 404 raised halfway through a multi-step write
    would otherwise persist the first half.
    """
    name = f"{PROBE} rollback"
    # `get_session` is annotated as returning an Iterator; it is a generator, and
    # `throw` is how FastAPI propagates a handler's exception into the dependency.
    generator: Generator[Session, None, None] = get_session()  # type: ignore[assignment]
    session = next(generator)
    session.execute(text("INSERT INTO institutions (name) VALUES (:n)"), {"n": name})

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("handler blew up"))

    assert _count(engine, name) == 0
