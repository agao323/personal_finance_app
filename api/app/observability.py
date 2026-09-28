"""Sentry initialisation.

Cleanly disabled when no DSN is set, so local development and tests never emit
events and never need a network call.

Sentry breadcrumbs are the sneakiest version of the leak this project cares about:
an error report can carry the request body that caused it, and for this app that
body is a balance. Request bodies are therefore never captured, stack frames carry no
local variables, exception messages are withheld, and any monetary field surviving
elsewhere in the event is redacted with the same filter the logs use.
"""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.logging import redact

#: What an exception's message becomes in an error report. The type and the stack stay.
MESSAGE_WITHHELD = "[message withheld]"


def _scrub(event: Event, _hint: Hint) -> Event | None:
    """Strip request payloads, exception messages and monetary fields before an event leaves."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        # A query string can carry as_of/amount pairs; drop rather than parse.
        request.pop("query_string", None)

    # An exception's message can quote data: Postgres puts the offending value in its own
    # error text ("invalid input syntax …: "$1,234.56"", "Failing row contains (…)"), which
    # `hide_parameters` cannot reach, and a validation error echoes its input. The type
    # and the stack are enough to find the line; the message goes.
    exceptions = event.get("exception")
    if isinstance(exceptions, dict):
        for value in exceptions.get("values") or []:
            if isinstance(value, dict) and value.get("value"):
                value["value"] = MESSAGE_WITHHELD

    scrubbed: Event = redact(event)
    return scrubbed


def configure_sentry(
    dsn: str | None, environment: str = "development", transport: Any = None
) -> bool:
    """Initialise Sentry. Returns whether it was enabled.

    `transport` exists for the tests, which capture events instead of sending them.
    """
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        # No PII, and never the request body — see module docstring.
        send_default_pii=False,
        max_request_body_size="never",
        # On by default: every stack frame's local variables go with the event. A frame in
        # the advisor's loop holds prompts and tool results, and a frame anywhere else can
        # hold a balance; `_scrub` redacts monetary *keys*, not "$1,234.56" inside a
        # string. Off, for the whole API.
        include_local_variables=False,
        before_send=_scrub,
        traces_sample_rate=0.0,
        transport=transport,
    )
    return True


def report_advisor_failure(where: str, error: str, **ids: str | None) -> None:
    """An advisor failure for Sentry: where it happened, the error's class, and ids. Nothing else.

    The loop and the tool registry catch their exceptions — a failed lookup is a result the
    model can act on, and a failed turn is an `error` event — so Sentry would never see
    them. This reports each one without the exception itself, whose message could carry a
    figure, and without a stack. See docs/ADVISOR.md#audit-and-observability.
    """
    tags = {f"advisor.{key}": value for key, value in ids.items() if value is not None}
    tags["advisor.where"] = where
    tags["advisor.error"] = error
    sentry_sdk.capture_message(f"advisor {where} failed: {error}", level="error", tags=tags)
