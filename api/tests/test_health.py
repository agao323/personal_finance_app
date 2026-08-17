"""Functional tests for the liveness and readiness endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app import main
from app.main import app


@pytest.fixture
def bare_client() -> Iterator[TestClient]:
    """A client with no database fixtures — proves /health needs nothing."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(bare_client: TestClient) -> None:
    response = bare_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_touch_the_database(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the liveness/readiness split.

    If /health ever grows a database call, Fly's probe will restart healthy
    instances during a transient database problem. Make the engine explode; /health
    must not notice.
    """

    def explode() -> Engine:
        raise AssertionError("/health must not open a database connection")

    monkeypatch.setattr(main, "get_engine", explode)

    assert bare_client.get("/health").status_code == 200


def test_ready_reports_database_reachable(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


def test_ready_returns_503_when_database_unreachable(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Port 1 refuses immediately, so this stays fast and needs no live database."""
    unreachable = create_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing",
        connect_args={"prepare_threshold": None},
    )
    monkeypatch.setattr(main, "get_engine", lambda: unreachable)

    response = bare_client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": False}
