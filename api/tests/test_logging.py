"""Tests for structured logging, redaction, and request context.

The redaction tests are the ones that matter. Everything else in this file is
plumbing; a leak here puts real balances into a log aggregator, backups, and a
vendor's search index.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logging import (
    REDACTED,
    configure_logging,
    is_monetary_key,
    redact,
    redaction_processor,
)
from app.middleware import REQUEST_ID_HEADER, RequestContextMiddleware

# ── redaction ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "amount",
        "balance",
        "total",
        "net_worth",
        "price",
        "Balance",
        "AMOUNT",
        "opening_balance",
        "closing_total",
        "starting_amount",
        "balance_cents",
        "purchase_price",
    ],
)
def test_monetary_keys_are_recognised(key: str) -> None:
    assert is_monetary_key(key)


@pytest.mark.parametrize(
    "key",
    ["method", "path", "status", "request_id", "account_id", "as_of", "currency", "name"],
)
def test_non_monetary_keys_are_left_alone(key: str) -> None:
    assert not is_monetary_key(key)


def test_redacts_a_flat_dict() -> None:
    assert redact({"balance": 1234.56, "account_id": 7}) == {
        "balance": REDACTED,
        "account_id": 7,
    }


def test_redacts_nested_dicts() -> None:
    payload = {"account": {"name": "Checking", "balance": 999, "meta": {"total": 5}}}

    assert redact(payload) == {
        "account": {"name": "Checking", "balance": REDACTED, "meta": {"total": REDACTED}}
    }


def test_redacts_dicts_inside_lists() -> None:
    payload = {"accounts": [{"id": 1, "balance": 10}, {"id": 2, "balance": 20}]}

    assert redact(payload) == {
        "accounts": [{"id": 1, "balance": REDACTED}, {"id": 2, "balance": REDACTED}]
    }


def test_redacts_deeply_nested_lists_of_lists() -> None:
    payload = {"rows": [[{"amount": 1}], [{"amount": 2}]]}

    assert redact(payload) == {"rows": [[{"amount": REDACTED}], [{"amount": REDACTED}]]}


def test_redacts_tuples() -> None:
    assert redact({"pair": ({"total": 1}, {"id": 2})}) == {"pair": ({"total": REDACTED}, {"id": 2})}


def test_processor_redacts_top_level_event_fields() -> None:
    event = {"event": "recorded", "balance": 42, "account_id": 1}

    assert redaction_processor(None, "info", event) == {
        "event": "recorded",
        "balance": REDACTED,
        "account_id": 1,
    }


def test_redaction_leaves_non_containers_untouched() -> None:
    assert redact("plain") == "plain"
    assert redact(7) == 7
    assert redact(None) is None


# ── request logging ───────────────────────────────────────────────────────────


def test_request_id_is_returned_to_the_caller(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers[REQUEST_ID_HEADER]


def test_inbound_request_id_is_honoured(client: TestClient) -> None:
    """Lets a request be correlated across the proxy hop rather than restarting."""
    response = client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc123"


def test_successful_request_logs_one_line(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")
    capsys.readouterr()

    client.get("/health", headers={REQUEST_ID_HEADER: "req-1"})

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]
    events = [json.loads(ln) for ln in lines]
    requests = [e for e in events if e.get("event") == "request"]

    assert len(requests) == 1
    entry = requests[0]
    assert entry["request_id"] == "req-1"
    assert entry["method"] == "GET"
    assert entry["path"] == "/health"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], (int, float))


# ── unhandled exceptions ──────────────────────────────────────────────────────


@pytest.fixture
def exploding_client() -> Iterator[TestClient]:
    """A minimal app with the same middleware and a route that raises."""
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)

    @test_app.get("/boom")
    def boom() -> dict[str, Any]:
        raise ValueError("account balance was 12345.67")

    # raise_server_exceptions=False so the client returns the 500 instead of
    # re-raising, which is what a real caller sees.
    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_unhandled_exception_logs_exactly_one_line(
    exploding_client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")
    capsys.readouterr()

    response = exploding_client.get("/boom", headers={REQUEST_ID_HEADER: "req-boom"})
    assert response.status_code == 500

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]
    failures = [json.loads(ln) for ln in lines if '"request_failed"' in ln]

    assert len(failures) == 1
    assert failures[0]["request_id"] == "req-boom"
    assert failures[0]["path"] == "/boom"


def test_failure_log_carries_no_monetary_field(
    exploding_client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A structured field named like money must never survive to the output."""
    configure_logging("INFO")
    capsys.readouterr()

    exploding_client.get("/boom")

    out = capsys.readouterr().out
    failures = [
        json.loads(ln)
        for ln in out.splitlines()
        if ln.strip().startswith("{") and '"request_failed"' in ln
    ]

    assert failures
    for entry in failures:
        for key, value in entry.items():
            if is_monetary_key(key):
                assert value == REDACTED
