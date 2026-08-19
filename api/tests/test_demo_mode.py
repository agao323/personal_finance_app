"""Tests for the demo deployment's read-only lock.

**This is not the demo's security boundary** and these tests are not what makes the
demo safe. The boundary is that the demo holds credentials for a different Neon project
and cannot reach the real database — see docs/adr/0003-demo-isolation.md. What this
covers is the demo's own data: it is public and unauthenticated, so without the lock
anyone could rewrite the numbers everyone else sees.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def demo_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_every_mutating_verb_is_rejected(client: TestClient, demo_mode: None) -> None:
    """Enforced in middleware, so a route added later is covered by default.

    A demo lock that each new endpoint has to remember is not a lock — and the list
    below is a sample, not the enforcement.
    """
    for method, path in (
        ("POST", "/accounts"),
        ("PATCH", "/accounts/1"),
        ("POST", "/accounts/1/balances"),
        ("POST", "/accounts/1/stakes"),
        ("POST", "/transactions/bulk-categorise"),
        ("POST", "/transactions/bulk-transfer"),
        ("PATCH", "/transactions/1"),
        ("POST", "/rules"),
        ("PATCH", "/rules/1"),
        ("DELETE", "/rules/1"),
        ("POST", "/rules/apply"),
        ("POST", "/rules/preview"),
        ("POST", "/import/csv/commit"),
        ("POST", "/auth/register/options"),
        ("POST", "/auth/login/verify"),
    ):
        response = client.request(method, path, json={})
        assert response.status_code == 405, f"{method} {path} returned {response.status_code}"


def test_no_declared_route_can_be_written_to(client: TestClient, demo_mode: None) -> None:
    """The real assertion: walk the app, not a hand-written list.

    A route added after this test was written is the exact thing a sample would miss.
    """
    from tests.test_contract import _api_routes

    writable: list[str] = []
    for route in _api_routes():
        for method in sorted(route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            path = (
                route.path.replace("{account_id}", "1")
                .replace("{rule_id}", "1")
                .replace("{transaction_id}", "1")
            )
            if client.request(method, path, json={}).status_code != 405:
                writable.append(f"{method} {route.path}")

    assert not writable, f"writable under DEMO_MODE: {sorted(writable)}"


def test_the_response_says_which_methods_are_allowed(client: TestClient, demo_mode: None) -> None:
    """405 with an Allow header, not 403: the resource is readable, the verb is not."""
    response = client.post("/rules", json={})

    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD, OPTIONS"
    assert "read-only demo" in response.json()["detail"]


def test_reads_are_untouched(client: TestClient, demo_mode: None) -> None:
    """A read-only demo that cannot be read is not a demo."""
    for path in ("/health", "/ready", "/net-worth", "/accounts", "/spend", "/transactions"):
        assert client.get(path).status_code == 200, path


def test_writes_work_normally_when_the_flag_is_off(
    client: TestClient, make_account: Callable[..., int]
) -> None:
    """Off by default. The real deployment must never be read-only."""
    account_id = make_account()

    response = client.post(
        f"/accounts/{account_id}/balances",
        json={"as_of": "2026-03-01", "balance_cents": 1000},
    )

    assert response.status_code in (200, 201)
