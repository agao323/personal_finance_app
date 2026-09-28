"""The loop, end to end against the scripted model: events, tools, caps, stops, the store.

Every test runs a real turn — the registry, read-only tool sessions, the database store —
with only the model replaced. Nothing here reaches a network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.advisor import loop
from app.advisor.loop import TurnDeps, run_turn, to_api_messages, turn_context
from app.advisor.model import (
    ModelRequest,
    ModelResponse,
    ScriptedCall,
    ScriptedModelClient,
    TextDelta,
    ToolUse,
    Usage,
)
from app.advisor.store import (
    Store,
    StoredMessage,
    months_before,
    nested_in,
)
from app.advisor.tools import load_all, savepoint_read_only
from app.config import Settings, get_settings
from app.models.advisor import (
    AdvisorConversation,
    AdvisorMessage,
    AdvisorToolCall,
    AdvisorTurn,
    AdvisorUsage,
)
from app.schemas.advisor import AdvisorErrorCode, AdvisorEvent
from app.schemas.common import ViewScope

NOW = dt.datetime(2026, 9, 27, 15, 0, tzinfo=dt.UTC)
REGISTRY = load_all()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql://unused",
        "advisor_enabled": True,
        "anthropic_api_key": SecretStr("test-key-not-real"),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def store(db_session: Session) -> Store:
    return Store(nested_in(db_session))


@pytest.fixture
def conversation(store: Store, owner_id: int) -> uuid.UUID:
    return store.create_conversation(owner_id, "mine", "Net worth?", NOW)


class Harness:
    """Runs turns against one conversation and collects what they emitted."""

    def __init__(
        self, db_session: Session, store: Store, conversation: uuid.UUID, owner_id: int
    ) -> None:
        self.db = db_session
        self.store = store
        self.conversation = conversation
        self.owner_id = owner_id

    def deps(self, client: Any, **overrides: Any) -> TurnDeps:
        settings = overrides.pop("settings", None) or _settings()
        overrides.setdefault("now", lambda: NOW)
        return TurnDeps(
            client=client,
            store=self.store,
            registry=REGISTRY,
            tool_sessions=savepoint_read_only(self.db),
            settings=settings,
            **overrides,
        )

    def run(
        self,
        client: Any,
        question: str = "What's my net worth?",
        view: ViewScope = ViewScope.MINE,
        **overrides: Any,
    ) -> list[dict[str, Any]]:
        async def collect() -> list[dict[str, Any]]:
            stream = run_turn(
                self.deps(client, **overrides),
                conversation_id=self.conversation,
                user_id=self.owner_id,
                view=view,
                question=question,
            )
            return [event.model_dump(mode="json") async for event in stream]

        return asyncio.run(collect())

    def turns(self) -> list[AdvisorTurn]:
        self.db.expire_all()
        return list(
            self.db.execute(
                select(AdvisorTurn)
                .where(AdvisorTurn.conversation_id == self.conversation)
                .order_by(AdvisorTurn.seq)
            ).scalars()
        )

    def roles(self, turn: AdvisorTurn) -> list[str]:
        return [m.role for m in sorted(turn.messages, key=lambda m: m.seq)]

    def count(self, model: type[Any]) -> int:
        return int(self.db.execute(select(func.count()).select_from(model)).scalar_one())


@pytest.fixture
def harness(db_session: Session, store: Store, conversation: uuid.UUID, owner_id: int) -> Harness:
    return Harness(db_session, store, conversation, owner_id)


def types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def _tool(name: str, args: dict[str, Any], tool_id: str = "toolu_1") -> ToolUse:
    return ToolUse(id=tool_id, name=name, input=args)


def _paid(**overrides: Any) -> ScriptedModelClient:
    """A scripted client that costs money, so the caps have something to count."""
    return ScriptedModelClient(provider="anthropic", model="claude-opus-5", **overrides)


# ── a turn, end to end ────────────────────────────────────────────────────────


def test_a_two_tool_turn_end_to_end(harness: Harness) -> None:
    def results_came_back(request: ModelRequest) -> None:
        last = request.messages[-1]
        assert last["role"] == "user"
        assert [b["tool_use_id"] for b in last["content"]] == ["toolu_1", "toolu_2"]
        assert all(b["type"] == "tool_result" for b in last["content"])

    client = ScriptedModelClient(
        [
            ScriptedCall(
                text=["Let me look."],
                tool_calls=[
                    _tool("networth_get", {"view": None}, "toolu_1"),
                    _tool("categories_list", {}, "toolu_2"),
                ],
            ),
            ScriptedCall(text=["Your net worth ", "is shown above."], expect=results_came_back),
        ]
    )

    events = harness.run(client)

    assert types(events) == [
        "turn_started",
        "text_delta",
        "tool_call",
        "tool_call",
        "text_delta",
        "text_delta",
        "answer",
        "turn_complete",
    ]
    for event in events:
        AdvisorEvent.model_validate(event)  # every event is a member of the streamed union
    assert [e["lookup"]["call_id"] for e in events if e["type"] == "tool_call"] == ["c1", "c2"]
    assert all(e["lookup"]["status"] == "ok" for e in events if e["type"] == "tool_call")
    answer = next(e for e in events if e["type"] == "answer")["answer"]
    assert answer["text"] == "Your net worth is shown above."
    assert [c["call_id"] for c in answer["citations"]] == ["c1", "c2"]
    assert answer["truncated"] is False

    (turn,) = harness.turns()
    assert turn.status == "complete"
    assert turn.model == "scripted"
    assert harness.roles(turn) == ["user", "context", "assistant", "tool_results", "assistant"]
    calls = harness.db.execute(select(AdvisorToolCall).order_by(AdvisorToolCall.id)).scalars().all()
    assert [(c.tool_name, c.tool_call_id, c.status) for c in calls] == [
        ("networth_get", "c1", "ok"),
        ("categories_list", "c2", "ok"),
    ]
    assert harness.count(AdvisorUsage) == 2
    assert events[-1]["cost_cents"] == 0  # scripted calls are free


def test_the_prompt_is_static_and_the_date_and_view_are_per_turn(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["Hi."])], model="claude-opus-5")

    harness.run(client, view=ViewScope.HOUSEHOLD)

    (request,) = client.requests
    assert list(request.system) == [loop.system_prompt()]
    assert "2026" not in loop.system_prompt()
    assert request.messages[-1] == {
        "role": "system",
        "content": [{"type": "text", "text": turn_context(NOW.date(), ViewScope.HOUSEHOLD)}],
    }
    assert "2026-09-27" in request.messages[-1]["content"][0]["text"]
    assert "Household" in request.messages[-1]["content"][0]["text"]
    (turn,) = harness.turns()
    expected = hashlib.sha256(loop.PROMPT_PATH.read_bytes()).hexdigest()
    assert turn.prompt_version == expected


def test_a_model_without_system_messages_reads_the_context_in_the_user_turn(
    harness: Harness,
) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["Hi."])], model="claude-sonnet-5")

    harness.run(client, question="Hello?")

    (request,) = client.requests
    assert [m["role"] for m in request.messages] == ["user"]
    texts = [b["text"] for b in request.messages[0]["content"]]
    assert texts[0].startswith("Today is")
    assert texts[1] == "Hello?"


def test_context_after_tool_results_follows_them() -> None:
    turn = uuid.uuid4()
    result = {"type": "tool_result", "tool_use_id": "t", "content": "x"}
    note = {"type": "text", "text": "No more lookups."}
    stored = [
        StoredMessage(turn, "user", [{"type": "text", "text": "q"}]),
        StoredMessage(
            turn, "assistant", [{"type": "tool_use", "id": "t", "name": "n", "input": {}}]
        ),
        StoredMessage(turn, "tool_results", [result]),
        StoredMessage(turn, "context", [note]),
    ]

    messages = to_api_messages(stored, system_messages=False)

    assert messages[-1] == {"role": "user", "content": [result, note]}
    assert to_api_messages(stored, system_messages=True)[-1] == {
        "role": "system",
        "content": [note],
    }


def test_invalid_arguments_go_back_to_the_model_as_an_error(harness: Harness) -> None:
    def saw_the_error(request: ModelRequest) -> None:
        (block,) = request.messages[-1]["content"]
        assert block["is_error"] is True
        assert "view" in block["content"]

    client = ScriptedModelClient(
        [
            ScriptedCall(tool_calls=[_tool("networth_get", {"view": "everyone"})]),
            ScriptedCall(text=["Sorry."], expect=saw_the_error),
        ]
    )

    events = harness.run(client)

    lookup = next(e for e in events if e["type"] == "tool_call")["lookup"]
    assert lookup["status"] == "invalid_args"
    call = harness.db.execute(select(AdvisorToolCall)).scalar_one()
    assert call.status == "invalid_args"
    assert types(events)[-2:] == ["answer", "turn_complete"]


def test_call_ids_carry_on_across_turns(harness: Harness) -> None:
    first = ScriptedModelClient(
        [
            ScriptedCall(
                tool_calls=[
                    _tool("categories_list", {}, "a"),
                    _tool("categories_list", {}, "b"),
                ]
            ),
            ScriptedCall(text=["One."]),
        ]
    )
    second = ScriptedModelClient(
        [ScriptedCall(tool_calls=[_tool("categories_list", {})]), ScriptedCall(text=["Two."])]
    )

    harness.run(first)
    events = harness.run(second)

    assert next(e for e in events if e["type"] == "tool_call")["lookup"]["call_id"] == "c3"


# ── budgets ───────────────────────────────────────────────────────────────────


def test_the_last_model_call_has_tools_off(harness: Harness) -> None:
    client = ScriptedModelClient(
        [
            ScriptedCall(tool_calls=[_tool("categories_list", {})]),
            ScriptedCall(text=["With what I have: ..."]),
        ]
    )

    events = harness.run(client, max_model_calls=2)

    first, final = client.requests
    assert first.tools_enabled is True
    assert final.tools_enabled is False
    assert [t.name for t in final.tools] == REGISTRY.names()
    # "scripted" takes no system messages, so the note follows the tool results.
    assert final.messages[-1]["content"][-1]["text"] == loop.FINAL_CALL_CONTEXT
    assert types(events)[-2:] == ["answer", "turn_complete"]


def test_a_tool_call_on_the_final_call_is_not_run(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(tool_calls=[_tool("categories_list", {})])])

    events = harness.run(client, max_model_calls=1)

    assert events[-2]["code"] == "model_error"
    assert harness.count(AdvisorToolCall) == 0


def test_the_thirteenth_lookup_is_refused(harness: Harness) -> None:
    many = [_tool("categories_list", {}, f"t{i}") for i in range(13)]
    client = ScriptedModelClient(
        [ScriptedCall(tool_calls=many), ScriptedCall(text=["Here is what I found."])]
    )

    events = harness.run(client)

    statuses = [e["lookup"]["status"] for e in events if e["type"] == "tool_call"]
    assert statuses == ["ok"] * 12 + ["budget_exhausted"]
    assert harness.count(AdvisorToolCall) == 13
    assert types(events)[-2:] == ["answer", "turn_complete"]


def test_the_wall_clock_stops_a_slow_model(harness: Harness) -> None:
    class Slow:
        provider = "scripted"
        model = "scripted"

        async def stream(self, request: ModelRequest) -> AsyncIterator[Any]:
            yield TextDelta("Thinking")
            await asyncio.sleep(5)
            yield TextDelta("never")

    events = harness.run(Slow(), turn_seconds=0.2)

    assert types(events) == ["turn_started", "text_delta", "error", "turn_complete"]
    assert events[2]["code"] == "timeout"
    assert harness.turns()[0].status == "failed"


# ── caps and the switch ───────────────────────────────────────────────────────


def _usage_row(
    db: Session, *, output_tokens: int, turn_id: uuid.UUID | None = None, at: dt.datetime = NOW
) -> None:
    db.add(
        AdvisorUsage(
            turn_id=turn_id,
            provider="anthropic",
            model="claude-opus-5",
            input_tokens=0,
            output_tokens=output_tokens,
            latency_ms=1,
            created_at=at,
        )
    )
    db.flush()


def test_the_monthly_cap_refuses_before_any_spend(harness: Harness) -> None:
    # $19.95 already spent this month: 798,000 output tokens at $25/MTok.
    _usage_row(harness.db, output_tokens=798_000)
    client = _paid(script=[ScriptedCall(text=["x"])])

    events = harness.run(client)

    assert events == [
        {
            "type": "error",
            "code": "monthly_cap",
            "message": loop.MESSAGES[AdvisorErrorCode.MONTHLY_CAP],
            "resets_on": "2026-10-01",
        }
    ]
    assert client.requests == []
    assert harness.turns() == []


def test_last_months_spend_does_not_count(harness: Harness) -> None:
    _usage_row(harness.db, output_tokens=798_000, at=NOW - dt.timedelta(days=30))
    client = _paid(script=[ScriptedCall(text=["x"])])

    assert types(harness.run(client))[-1] == "turn_complete"


def test_the_conversation_cap_refuses_before_any_spend(harness: Harness) -> None:
    turn = AdvisorTurn(conversation_id=harness.conversation, seq=1, status="complete")
    harness.db.add(turn)
    harness.db.flush()
    # $1.95 already spent in this conversation.
    _usage_row(harness.db, output_tokens=78_000, turn_id=turn.id)
    client = _paid(script=[ScriptedCall(text=["x"])])

    events = harness.run(client)

    assert [e["code"] for e in events] == ["conversation_cap"]
    assert client.requests == []


def test_the_turn_cap_refuses_before_the_call_that_would_cross_it(harness: Harness) -> None:
    client = _paid(script=[ScriptedCall(text=["x"])])

    events = harness.run(client, settings=_settings(advisor_turn_cap_cents=1))

    assert types(events) == ["turn_started", "error", "turn_complete"]
    assert events[1]["code"] == "turn_cap"
    assert client.requests == []
    assert harness.count(AdvisorUsage) == 0
    assert harness.turns()[0].error_code == "turn_cap"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"advisor_enabled": False}, "disabled"),
        ({"demo_mode": True}, "demo"),
    ],
)
def test_the_kill_switch_and_the_demo_refuse(
    harness: Harness, overrides: dict[str, Any], code: str
) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["x"])])

    events = harness.run(client, settings=_settings(**overrides))

    assert [e["code"] for e in events] == [code]
    assert client.requests == []
    assert harness.turns() == []


def test_one_turn_at_a_time(harness: Harness) -> None:
    harness.db.add(
        AdvisorTurn(conversation_id=harness.conversation, seq=1, status="streaming", started_at=NOW)
    )
    harness.db.flush()
    client = ScriptedModelClient([ScriptedCall(text=["x"])])

    assert [e["code"] for e in harness.run(client)] == ["turn_in_progress"]


def test_a_turn_abandoned_by_a_dead_process_is_closed(harness: Harness) -> None:
    harness.db.add(
        AdvisorTurn(
            conversation_id=harness.conversation,
            seq=1,
            status="streaming",
            started_at=NOW - dt.timedelta(minutes=10),
        )
    )
    harness.db.flush()
    client = ScriptedModelClient([ScriptedCall(text=["x"])])

    events = harness.run(client)

    assert types(events)[-1] == "turn_complete"
    old, new = harness.turns()
    assert (old.status, old.error_code) == ("failed", "timeout")
    assert new.status == "complete"


# ── stop reasons ──────────────────────────────────────────────────────────────


def test_a_truncated_tool_call_is_never_run(harness: Harness) -> None:
    client = ScriptedModelClient(
        [ScriptedCall(tool_calls=[_tool("categories_list", {})], stop_reason="max_tokens")]
    )

    events = harness.run(client)

    assert [e["code"] for e in events if e["type"] == "error"] == ["truncated"]
    assert harness.count(AdvisorToolCall) == 0
    assert harness.turns()[0].status == "failed"


def test_truncated_text_is_delivered_marked(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["The answer is"], stop_reason="max_tokens")])

    events = harness.run(client)

    answer = next(e for e in events if e["type"] == "answer")["answer"]
    assert answer["truncated"] is True
    assert harness.turns()[0].status == "complete"


def test_a_refusal_is_explained(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(stop_reason="refusal")])

    events = harness.run(client)

    assert [e["code"] for e in events if e["type"] == "error"] == ["refusal"]
    (turn,) = harness.turns()
    assert (turn.status, turn.error_code) == ("refused", "refusal")


def test_pause_turn_is_an_error(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["x"], stop_reason="pause_turn")])

    assert [e["code"] for e in harness.run(client) if e["type"] == "error"] == ["model_error"]


def test_a_provider_failure_is_a_model_error_and_keeps_the_audit(harness: Harness) -> None:
    client = ScriptedModelClient(
        [
            ScriptedCall(tool_calls=[_tool("categories_list", {})]),
            ScriptedCall(text=["Half"], raises=ConnectionError("reset")),
        ]
    )

    events = harness.run(client)

    assert types(events)[-2:] == ["error", "turn_complete"]
    assert events[-2]["code"] == "model_error"
    assert harness.count(AdvisorToolCall) == 1
    assert harness.count(AdvisorUsage) == 1
    assert harness.turns()[0].status == "failed"


# ── cancellation ──────────────────────────────────────────────────────────────


def test_cancelling_mid_stream_closes_the_model_and_keeps_the_audit(harness: Harness) -> None:
    closed: list[bool] = []

    class Streaming:
        provider = "scripted"
        model = "scripted"

        def __init__(self) -> None:
            self.inner = ScriptedModelClient(
                [ScriptedCall(tool_calls=[_tool("categories_list", {})])]
            )
            self.calls = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[Any]:
            self.calls += 1
            if self.calls == 1:
                async for event in self.inner.stream(request):
                    yield event
                return
            try:
                yield TextDelta("Your net")
                yield TextDelta(" worth is")
                yield ModelResponse("end_turn", Usage(), "scripted", None, [])
            finally:
                closed.append(True)

    async def cancel_after_first_word() -> list[str]:
        seen: list[str] = []
        stream = run_turn(
            harness.deps(Streaming()),
            conversation_id=harness.conversation,
            user_id=harness.owner_id,
            view=ViewScope.MINE,
            question="Net worth?",
        )
        async for event in stream:
            seen.append(event.model_dump()["type"])
            if seen[-1] == "text_delta":
                await stream.aclose()  # type: ignore[attr-defined]
                break
        return seen

    seen = asyncio.run(cancel_after_first_word())

    assert seen == ["turn_started", "tool_call", "text_delta"]
    assert closed == [True]
    (turn,) = harness.turns()
    assert (turn.status, turn.error_code) == ("cancelled", "cancelled")
    assert harness.count(AdvisorToolCall) == 1
    assert harness.count(AdvisorUsage) == 1


# ── history ───────────────────────────────────────────────────────────────────


def test_history_is_replayed_byte_for_byte(harness: Harness) -> None:
    first = ScriptedModelClient(
        [
            ScriptedCall(text=["Checking."], tool_calls=[_tool("networth_get", {"view": None})]),
            ScriptedCall(text=["Here it is."]),
        ]
    )
    second = ScriptedModelClient([ScriptedCall(text=["And again."])])

    harness.run(first, question="First?")
    harness.run(second, question="Second?")

    last_of_first = first.requests[-1].messages
    final_answer = {"role": "assistant", "content": [{"type": "text", "text": "Here it is."}]}
    replayed = second.requests[0].messages[: len(last_of_first) + 1]
    assert json.dumps(replayed) == json.dumps([*last_of_first, final_answer])
    assert second.requests[0].messages[len(last_of_first) + 1]["content"][-1]["text"] == "Second?"


def test_an_unfinished_turn_is_not_replayed(harness: Harness) -> None:
    refused = ScriptedModelClient([ScriptedCall(stop_reason="refusal")])
    later = ScriptedModelClient([ScriptedCall(text=["Fine."])])

    harness.run(refused, question="Refused question?")
    harness.run(later, question="Later?")

    texts = json.dumps(later.requests[0].messages)
    assert "Refused question?" not in texts
    assert "Later?" in texts


# ── the store ─────────────────────────────────────────────────────────────────


def test_purge_boundaries(harness: Harness, store: Store, owner_id: int) -> None:
    db = harness.db
    expired = store.create_conversation(owner_id, "mine", "old", NOW - dt.timedelta(days=30))
    alive = store.create_conversation(
        owner_id, "mine", "recent", NOW - dt.timedelta(days=30) + dt.timedelta(seconds=1)
    )

    def call(age: dt.timedelta) -> None:
        db.add(
            AdvisorToolCall(
                tool_name="t",
                tool_call_id="c1",
                args={},
                status="ok",
                latency_ms=0,
                row_count=0,
                result_bytes=0,
                withheld_count=0,
                created_at=NOW - age,
            )
        )

    call(dt.timedelta(days=90))
    call(dt.timedelta(days=90, seconds=1))
    thirteen = months_before(NOW, 13)
    _usage_row(db, output_tokens=1, at=thirteen)
    _usage_row(db, output_tokens=1, at=thirteen - dt.timedelta(seconds=1))
    db.flush()

    purged = store.purge(NOW)

    assert (purged.conversations, purged.tool_calls, purged.usage) == (1, 1, 1)
    db.expire_all()
    assert db.get(AdvisorConversation, expired) is None
    assert db.get(AdvisorConversation, alive) is not None
    assert harness.count(AdvisorToolCall) == 1
    assert harness.count(AdvisorUsage) == 1


def test_a_turn_pushes_the_expiry_back(harness: Harness) -> None:
    later = NOW + dt.timedelta(days=10)
    client = ScriptedModelClient([ScriptedCall(text=["x"])])

    harness.run(client, now=lambda: later)

    harness.db.expire_all()
    conversation = harness.db.get(AdvisorConversation, harness.conversation)
    assert conversation is not None
    assert conversation.expires_at == later + dt.timedelta(days=30)


def test_months_before_clamps_to_the_end_of_a_month() -> None:
    moment = dt.datetime(2027, 3, 31, 12, tzinfo=dt.UTC)

    assert months_before(moment, 1) == dt.datetime(2027, 2, 28, 12, tzinfo=dt.UTC)
    assert months_before(moment, 13) == dt.datetime(2026, 2, 28, 12, tzinfo=dt.UTC)
    assert months_before(moment, 12) == dt.datetime(2026, 3, 31, 12, tzinfo=dt.UTC)


def test_messages_are_stored_as_sent(harness: Harness) -> None:
    client = ScriptedModelClient([ScriptedCall(text=["Hello."])])

    harness.run(client, question="Hi?")

    messages = harness.db.execute(select(AdvisorMessage).order_by(AdvisorMessage.seq)).scalars()
    assert [(m.role, m.content) for m in messages] == [
        ("user", [{"type": "text", "text": "Hi?"}]),
        ("context", [{"type": "text", "text": turn_context(NOW.date(), ViewScope.MINE)}]),
        ("assistant", [{"type": "text", "text": "Hello."}]),
    ]


def test_the_worst_case_is_uncached_input_plus_full_output(harness: Harness) -> None:
    deps = harness.deps(_paid(script=[]))

    # 1,000 input at $5/MTok + 6,000 output at $25/MTok = $0.155
    assert loop._worst_case(deps, 1_000, NOW.date()) == Decimal("15.5")
    assert loop._worst_case(harness.deps(ScriptedModelClient([])), 1_000, NOW.date()) == 0


# ── GET /advisor/status ───────────────────────────────────────────────────────


@pytest.fixture
def advisor_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    def configure(**env: str) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield configure
    get_settings.cache_clear()


def test_status_is_off_by_default(client: TestClient) -> None:
    body = client.get("/advisor/status").json()

    assert body["enabled"] is False
    assert body["reason"] == "disabled"
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-opus-5"
    assert body["month_cap_cents"] == 2000


def test_status_names_a_missing_key(client: TestClient, advisor_env: Callable[..., None]) -> None:
    advisor_env(ADVISOR_ENABLED="true", ANTHROPIC_API_KEY="")

    assert client.get("/advisor/status").json()["reason"] == "not_configured"


def test_status_reports_month_to_date_spend(
    client: TestClient, db_session: Session, advisor_env: Callable[..., None]
) -> None:
    advisor_env(ADVISOR_ENABLED="true", ANTHROPIC_API_KEY="test-key-not-real")
    now = dt.datetime.now(dt.UTC)
    # 60,000 output tokens at $25/MTok = $1.50; 1 token = 0.0025 cents, rounded once.
    _usage_row(db_session, output_tokens=60_000, at=now)
    _usage_row(db_session, output_tokens=1, at=now)

    body = client.get("/advisor/status").json()

    assert body["enabled"] is True
    assert body["reason"] is None
    assert body["month_spent_cents"] == 150
    first_of_next = (now.date().replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    assert body["resets_on"] == first_of_next.isoformat()


def test_status_says_when_the_month_is_spent(
    client: TestClient, db_session: Session, advisor_env: Callable[..., None]
) -> None:
    advisor_env(ADVISOR_ENABLED="true", ANTHROPIC_API_KEY="test-key-not-real")
    _usage_row(db_session, output_tokens=800_000, at=dt.datetime.now(dt.UTC))

    body = client.get("/advisor/status").json()

    assert (body["enabled"], body["reason"]) == (False, "monthly_cap")
