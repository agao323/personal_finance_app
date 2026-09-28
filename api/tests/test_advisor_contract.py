"""The advisor and Insights contract, frozen by ticket 081.

`test_contract.py` already proves every route exists, answers 501 until it lands, is
documented, is authenticated, and carries money as integer cents. These pin what is
particular to this surface: the event union reaches the generated types, the streamed
routes say what really crosses the wire, and the enums ship complete.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.advisor import (
    AdvisorEvent,
    FindingKind,
    LimitationKind,
    TurnCreate,
    TurnFeedback,
)

EVENT_TYPES = {
    "turn_started",
    "tool_call",
    "text_delta",
    "answer",
    "regenerating",
    "error",
    "heartbeat",
    "turn_complete",
}


def _schemas() -> dict[str, Any]:
    components: dict[str, Any] = app.openapi()["components"]["schemas"]
    return components


def test_the_event_union_reaches_the_generated_types() -> None:
    """Only ever sent as SSE, so nothing would put it in the schema by accident."""
    event = _schemas()["AdvisorEvent"]

    assert set(event["discriminator"]["mapping"]) == EVENT_TYPES
    assert len(event["oneOf"]) == len(EVENT_TYPES)


def test_the_turn_route_is_documented_as_an_event_stream() -> None:
    """Filed under the media type that crosses the wire, not application/json."""
    response = app.openapi()["paths"]["/advisor/conversations/{conversation_id}/turns"]["post"][
        "responses"
    ]["200"]

    assert set(response["content"]) == {"text/event-stream"}
    assert response["content"]["text/event-stream"]["schema"]["$ref"].endswith("/AdvisorEvent")


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"type": "heartbeat"}, "heartbeat"),
        ({"type": "text_delta", "text": "Net worth is "}, "text_delta"),
        (
            {"type": "error", "code": "monthly_cap", "message": "Cap reached", "resets_on": None},
            "error",
        ),
    ],
)
def test_events_parse_by_their_discriminator(payload: dict[str, Any], kind: str) -> None:
    assert AdvisorEvent.model_validate(payload).root.type == kind


def test_an_unknown_event_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        AdvisorEvent.model_validate({"type": "tool_result", "data": {}})


def test_the_enums_ship_complete() -> None:
    """Later waves add findings and limitations without touching the contract."""
    assert {"goal_off_track", "allocation_drift", "cash_drag"} <= {k.value for k in FindingKind}
    assert {"market_data", "holdings", "liability_terms"} <= {k.value for k in LimitationKind}


def test_a_question_is_bounded() -> None:
    TurnCreate(question="x" * 2000)
    with pytest.raises(ValidationError):
        TurnCreate(question="x" * 2001)
    with pytest.raises(ValidationError):
        TurnCreate(question="")


def test_a_feedback_note_is_bounded() -> None:
    TurnFeedback(verdict="flagged", note="n" * 500)
    with pytest.raises(ValidationError):
        TurnFeedback(verdict="flagged", note="n" * 501)


def test_no_advisor_field_is_a_url() -> None:
    """Actions point at screens. A field that could carry a URL is one the UI might draw."""
    import app.schemas.advisor as advisor

    ours = {name for name in vars(advisor) if name[:1].isupper()}
    suspicious = {"url", "uri", "href", "link", "src", "image"}
    names = [
        (name, prop)
        for name, schema in _schemas().items()
        if name in ours
        for prop in schema.get("properties", {})
        if suspicious & set(prop.lower().split("_"))
    ]

    assert not names, f"fields that look like they carry a URL: {names}"
