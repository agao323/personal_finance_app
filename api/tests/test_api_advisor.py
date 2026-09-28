"""The advisor's HTTP surface: conversations, the streamed turn, feedback, the stream check.

Turns run the real loop and the real SSE layer against the scripted model. The store and the
tool sessions are pointed at the test's rolled-back session, which is the one thing that
differs from production — ADR 0005's fixture caveat, stated where it applies.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.advisor import sse
from app.advisor.loop import TurnDeps, run_turn
from app.advisor.model import ModelRequest, ScriptedCall, ScriptedModelClient, TextDelta, ToolUse
from app.advisor.store import Store, nested_in
from app.advisor.tools import load_all, savepoint_read_only
from app.config import Settings, get_settings
from app.main import app
from app.models.advisor import AdvisorToolCall, AdvisorTurn
from app.routers import advisor as advisor_router
from app.schemas.advisor import AdvisorEvent, TextDeltaEvent
from app.schemas.common import ViewScope

PARTNER = "partner@example.invalid"


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ADVISOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Model:
    """Swaps the model the streaming route uses; `script` sets the next turn's replies."""

    def __init__(self) -> None:
        self.client: Any = ScriptedModelClient([])

    def script(self, *calls: ScriptedCall, **kwargs: Any) -> ScriptedModelClient:
        scripted = ScriptedModelClient(list(calls), **kwargs)
        self.client = scripted
        return scripted


@pytest.fixture
def model(client: TestClient, db_session: Session) -> Iterator[Model]:
    swapped = Model()
    app.dependency_overrides[advisor_router.advisor_store] = lambda: Store(nested_in(db_session))
    app.dependency_overrides[advisor_router.advisor_tool_sessions] = lambda: savepoint_read_only(
        db_session
    )
    app.dependency_overrides[advisor_router.advisor_client] = lambda: swapped.client
    yield swapped
    for dependency in (
        advisor_router.advisor_store,
        advisor_router.advisor_tool_sessions,
        advisor_router.advisor_client,
    ):
        app.dependency_overrides.pop(dependency, None)


def _conversation(client: TestClient, view: str = "mine") -> str:
    response = client.post("/advisor/conversations", json={"view": view})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _ask(client: TestClient, conversation: str, question: str = "Net worth?") -> Any:
    return client.post(f"/advisor/conversations/{conversation}/turns", json={"question": question})


def _events(response: Any) -> list[dict[str, Any]]:
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
        else:
            assert line == "", f"unexpected line {line!r}"
    return events


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


@pytest.fixture
def as_partner(monkeypatch: pytest.MonkeyPatch, partner_id: int) -> Callable[[], None]:
    def switch() -> None:
        monkeypatch.setenv("DEV_IDENTITY_EMAIL", PARTNER)
        get_settings.cache_clear()

    return switch


# ── the streamed turn ─────────────────────────────────────────────────────────


def test_a_turn_streams_its_full_event_sequence(
    client: TestClient, model: Model, enabled: None
) -> None:
    model.script(
        ScriptedCall(tool_calls=[ToolUse("t1", "networth_get", {"view": None})]),
        ScriptedCall(text=["Mine: {{c1.net", "_worth}}."]),
    )
    conversation = _conversation(client)

    response = _ask(client, conversation)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    events = _events(response)
    for event in events:
        AdvisorEvent.model_validate(event)
    assert _types(events) == [
        "turn_started",
        "tool_call",
        "text_delta",
        "text_delta",
        "answer",
        "turn_complete",
    ]
    assert events[0]["conversation_id"] == conversation
    assert "".join(e["text"] for e in events if e["type"] == "text_delta") == "Mine: $0.00."
    assert events[-1]["grounding"] == "verified"


def test_the_first_question_titles_the_conversation(
    client: TestClient, model: Model, enabled: None
) -> None:
    model.script(ScriptedCall(text=["Hello."]))
    conversation = _conversation(client)
    assert client.get("/advisor/conversations").json()[0]["title"] == "New conversation"

    _ask(client, conversation, "What did we spend on dining?")

    (listed,) = client.get("/advisor/conversations").json()
    assert listed["title"] == "What did we spend on dining?"
    assert listed["turn_count"] == 1


def test_a_second_turn_while_one_streams_is_a_conflict(
    client: TestClient, model: Model, enabled: None, db_session: Session
) -> None:
    conversation = _conversation(client)
    db_session.add(
        AdvisorTurn(
            conversation_id=uuid.UUID(conversation),
            seq=1,
            status="streaming",
            started_at=dt.datetime.now(dt.UTC),
        )
    )
    db_session.flush()

    response = _ask(client, conversation)

    assert response.status_code == 409
    assert model.client.requests == []


def test_a_switched_off_advisor_says_so_in_the_stream(client: TestClient, model: Model) -> None:
    conversation = _conversation(client)

    events = _events(_ask(client, conversation))

    assert [(e["type"], e["code"]) for e in events] == [("error", "disabled")]


def test_no_key_is_not_configured(client: TestClient, model: Model, enabled: None) -> None:
    model.client = None
    conversation = _conversation(client)

    events = _events(_ask(client, conversation))

    assert [e["code"] for e in events] == ["not_configured"]


# ── heartbeats and disconnects ────────────────────────────────────────────────


async def _slow(events: list[BaseModel], pause: float) -> AsyncIterator[BaseModel]:
    for event in events:
        await asyncio.sleep(pause)
        yield event


def _decoded(chunks: list[bytes]) -> list[str]:
    return [json.loads(c.decode().removeprefix("data: "))["type"] for c in chunks]


def test_heartbeats_fill_the_silence() -> None:
    source = _slow([TextDeltaEvent(type="text_delta", text="a")] * 2, pause=0.25)

    async def collect() -> list[bytes]:
        stream = sse.stream_events(source, heartbeat_seconds=0.1, poll_seconds=0.01)
        return [chunk async for chunk in stream]

    kinds = _decoded(asyncio.run(collect()))

    assert kinds.count("text_delta") == 2
    assert kinds.count("heartbeat") >= 2
    assert kinds[0] == "heartbeat"


def test_no_heartbeat_when_events_keep_coming() -> None:
    source = _slow([TextDeltaEvent(type="text_delta", text="a")] * 5, pause=0.01)

    async def collect() -> list[bytes]:
        stream = sse.stream_events(source, heartbeat_seconds=1.0, poll_seconds=0.5)
        return [chunk async for chunk in stream]

    assert _decoded(asyncio.run(collect())) == ["text_delta"] * 5


def test_every_event_is_one_data_line() -> None:
    assert sse.encode(TextDeltaEvent(type="text_delta", text="a\nb")) == (
        b'data: {"type":"text_delta","text":"a\\nb"}\n\n'
    )


def test_a_disconnect_cancels_the_turn(db_session: Session, owner_id: int) -> None:
    store = Store(nested_in(db_session))
    conversation = store.create_conversation(owner_id, "mine", "", dt.datetime.now(dt.UTC))
    closed: list[bool] = []

    class Slow:
        provider = "scripted"
        model = "scripted"

        async def stream(self, request: ModelRequest) -> AsyncIterator[Any]:
            try:
                yield TextDelta("Thinking")
                await asyncio.sleep(10)
                yield TextDelta("never")
            finally:
                closed.append(True)

    deps = TurnDeps(
        client=Slow(),
        store=store,
        registry=load_all(),
        tool_sessions=savepoint_read_only(db_session),
        settings=Settings(
            database_url="postgresql://unused",
            advisor_enabled=True,
            anthropic_api_key=SecretStr("test-key-not-real"),
        ),
    )
    seen: list[str] = []

    async def gone() -> bool:
        return "text_delta" in seen

    async def listen() -> None:
        turn = run_turn(
            deps,
            conversation_id=conversation,
            user_id=owner_id,
            view=ViewScope.MINE,
            question="Net worth?",
        )
        async for chunk in sse.stream_events(turn, is_disconnected=gone, poll_seconds=0.01):
            seen.extend(_decoded([chunk]))

    asyncio.run(asyncio.wait_for(listen(), 5))

    assert seen == ["turn_started", "text_delta"]
    assert closed == [True]
    db_session.expire_all()
    turn = db_session.execute(select(AdvisorTurn)).scalar_one()
    assert (turn.status, turn.error_code) == ("cancelled", "cancelled")


def test_the_stream_check_sends_three_heartbeats(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(advisor_router, "STREAM_CHECK_SECONDS", 0.01)

    response = client.get("/advisor/stream-check")

    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert _events(response) == [{"type": "heartbeat"}] * 3


# ── conversations ─────────────────────────────────────────────────────────────


def test_create_and_list_newest_first(client: TestClient) -> None:
    first = _conversation(client, "mine")
    second = _conversation(client, "household")

    listed = client.get("/advisor/conversations").json()

    assert [c["id"] for c in listed] == [second, first]
    assert [c["view"] for c in listed] == ["household", "mine"]
    assert listed[0]["turn_count"] == 0


def test_the_detail_shows_answers_and_lookups_never_payloads(
    client: TestClient, model: Model, enabled: None
) -> None:
    model.script(
        ScriptedCall(tool_calls=[ToolUse("t1", "networth_get", {"view": None})]),
        ScriptedCall(text=["Mine: {{c1.net_worth}}."]),
    )
    conversation = _conversation(client)
    _ask(client, conversation, "What's my net worth?")

    response = client.get(f"/advisor/conversations/{conversation}")

    body = response.json()
    (turn,) = body["turns"]
    assert turn["question"] == "What's my net worth?"
    assert turn["status"] == "complete"
    assert turn["answer"]["text"] == "Mine: $0.00."
    assert [f["status"] for f in turn["answer"]["figures"]] == ["verified"]
    assert [c["tool"] for c in turn["answer"]["citations"]] == ["networth_get"]
    assert turn["answer"]["citations"][0]["view"] == "mine"
    (lookup,) = turn["lookups"]
    assert (lookup["call_id"], lookup["tool"], lookup["status"]) == ("c1", "networth_get", "ok")
    assert lookup["as_of"] is not None
    assert "tool_result" not in response.text
    assert "[c1.net_worth]" not in response.text  # the rendering the model read


def test_nobody_sees_or_deletes_anyone_elses(
    client: TestClient, as_partner: Callable[[], None]
) -> None:
    mine = _conversation(client)

    as_partner()

    assert client.get("/advisor/conversations").json() == []
    assert client.get(f"/advisor/conversations/{mine}").status_code == 404
    assert client.delete(f"/advisor/conversations/{mine}").status_code == 404
    theirs = _conversation(client)
    assert [c["id"] for c in client.get("/advisor/conversations").json()] == [theirs]


def test_delete_is_immediate_and_keeps_the_audit(
    client: TestClient, model: Model, enabled: None, db_session: Session
) -> None:
    model.script(
        ScriptedCall(tool_calls=[ToolUse("t1", "categories_list", {})]),
        ScriptedCall(text=["Here they are."]),
    )
    conversation = _conversation(client)
    _ask(client, conversation)

    assert client.delete(f"/advisor/conversations/{conversation}").status_code == 204

    assert client.get(f"/advisor/conversations/{conversation}").status_code == 404
    db_session.expire_all()
    call = db_session.execute(select(AdvisorToolCall)).scalar_one()
    assert (call.tool_name, call.conversation_id, call.turn_id) == ("categories_list", None, None)
    assert db_session.execute(select(func.count()).select_from(AdvisorTurn)).scalar_one() == 0


def test_an_unknown_conversation_is_not_found(client: TestClient, model: Model) -> None:
    missing = uuid.uuid4()

    assert client.get(f"/advisor/conversations/{missing}").status_code == 404
    assert _ask(client, str(missing)).status_code == 404


# ── feedback ──────────────────────────────────────────────────────────────────


def test_feedback_on_your_own_turn(
    client: TestClient, model: Model, enabled: None, as_partner: Callable[[], None]
) -> None:
    model.script(ScriptedCall(text=["Hello."]))
    conversation = _conversation(client)
    turn_id = _events(_ask(client, conversation))[0]["turn_id"]

    response = client.put(
        f"/advisor/turns/{turn_id}/feedback", json={"verdict": "flagged", "note": "Wrong period."}
    )

    assert response.status_code == 200
    assert (response.json()["feedback"], response.json()["feedback_note"]) == (
        "flagged",
        "Wrong period.",
    )
    detail = client.get(f"/advisor/conversations/{conversation}").json()
    assert detail["turns"][0]["feedback"] == "flagged"

    as_partner()
    refused = client.put(f"/advisor/turns/{turn_id}/feedback", json={"verdict": "good"})
    assert refused.status_code == 404


# ── the demo ──────────────────────────────────────────────────────────────────


def test_the_demo_refuses_every_advisor_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        missing = uuid.uuid4()
        assert client.get("/advisor/status").json()["reason"] == "demo"
        assert client.get("/advisor/conversations").status_code == 403
        assert client.get(f"/advisor/conversations/{missing}").status_code == 403
        assert client.post("/advisor/conversations", json={"view": "mine"}).status_code == 405
        assert _ask(client, str(missing)).status_code == 405
        assert client.delete(f"/advisor/conversations/{missing}").status_code == 405
        assert (
            client.put(f"/advisor/turns/{missing}/feedback", json={"verdict": "good"}).status_code
            == 405
        )
    finally:
        get_settings.cache_clear()
