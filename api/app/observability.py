"""Sentry initialisation.

Cleanly disabled when no DSN is set, so local development and tests never emit
events and never need a network call.

Sentry breadcrumbs are the sneakiest version of the leak this project cares about:
an error report can carry the request body that caused it, and for this app that
body is a balance. Request bodies are therefore never captured, and any monetary
field surviving elsewhere in the event is redacted with the same filter the logs
use.
"""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.logging import redact


def _scrub(event: Event, _hint: Hint) -> Event | None:
    """Strip request payloads and redact monetary fields before an event leaves."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        # A query string can carry as_of/amount pairs; drop rather than parse.
        request.pop("query_string", None)

    scrubbed: Event = redact(event)
    return scrubbed


def configure_sentry(dsn: str | None, environment: str = "development") -> bool:
    """Initialise Sentry. Returns whether it was enabled."""
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        # No PII, and never the request body — see module docstring.
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub,
        traces_sample_rate=0.0,
    )
    return True
