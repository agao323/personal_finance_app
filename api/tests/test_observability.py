"""Tests for Sentry configuration and event scrubbing.

Sentry breadcrumbs are the sneakiest version of the leak this project guards against:
an error report can carry the request body that caused it, and here that body is a
balance.
"""

from __future__ import annotations

from sentry_sdk.types import Event

from app.logging import REDACTED
from app.observability import _scrub, configure_sentry


def test_disabled_without_a_dsn() -> None:
    assert configure_sentry(None) is False
    assert configure_sentry("") is False


def test_scrub_drops_the_request_body() -> None:
    event: Event = {
        "request": {
            "url": "http://api/accounts",
            "method": "POST",
            "data": {"balance": "12345.67"},
        }
    }

    scrubbed = _scrub(event, {})

    assert scrubbed is not None
    assert "data" not in scrubbed["request"]
    assert scrubbed["request"]["url"] == "http://api/accounts"


def test_scrub_drops_cookies_and_query_string() -> None:
    event: Event = {"request": {"cookies": {"session": "x"}, "query_string": "amount=100"}}

    scrubbed = _scrub(event, {})

    assert scrubbed is not None
    assert "cookies" not in scrubbed["request"]
    assert "query_string" not in scrubbed["request"]


def test_scrub_redacts_monetary_fields_elsewhere_in_the_event() -> None:
    """Belt and braces: anything money-shaped that survives the drops is redacted."""
    event: Event = {
        "extra": {"net_worth": 500000, "account_id": 3},
        "contexts": {"account": {"balance": 12.34}},
    }

    scrubbed = _scrub(event, {})

    assert scrubbed is not None
    assert scrubbed["extra"]["net_worth"] == REDACTED
    assert scrubbed["extra"]["account_id"] == 3
    assert scrubbed["contexts"]["account"]["balance"] == REDACTED


def test_scrub_tolerates_an_event_with_no_request() -> None:
    event: Event = {"message": "hello"}
    assert _scrub(event, {}) == {"message": "hello"}
