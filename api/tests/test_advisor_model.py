"""The model client, the scripted fake, the price table, and the advisor's settings.

The Anthropic client is exercised through an `httpx2.MockTransport` — the 1.x SDK sends over
`httpx2`, not `httpx`, and refuses an `httpx` client. The real SDK builds and sends the
request; the transport captures it and answers with a canned event stream. No network, no key.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from app.advisor import pricing
from app.advisor.model import (
    FALLBACK_BETA,
    AnthropicModelClient,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ScriptedCall,
    ScriptedModelClient,
    TextDelta,
    ToolUse,
    Usage,
    supports_system_messages,
)
from app.advisor.tools import ToolDefinition, load_all
from app.config import Settings

TODAY = dt.date(2026, 9, 27)
TOOLS = [
    ToolDefinition("spend_by_category", "Spending.", {"type": "object", "properties": {}}),
    ToolDefinition("accounts_list", "Accounts.", {"type": "object", "properties": {}}),
]
REQUEST = ModelRequest(
    system=["You are the household's advisor.", "Tool guidance."],
    messages=[{"role": "user", "content": [{"type": "text", "text": "What's my net worth?"}]}],
    tools=TOOLS,
)


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


STREAM = _sse(
    {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 120,
                "cache_creation_input_tokens": 900,
                "cache_read_input_tokens": 7300,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 900,
                    "ephemeral_1h_input_tokens": 0,
                },
                "output_tokens": 1,
            },
        },
    },
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Let me "}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "check."}},
    {"type": "content_block_stop", "index": 0},
    {
        "type": "content_block_start",
        "index": 1,
        "content_block": {"type": "tool_use", "id": "toolu_1", "name": "networth_get", "input": {}},
    },
    {
        "type": "content_block_delta",
        "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '{"view": '},
    },
    {
        "type": "content_block_delta",
        "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '"mine"}'},
    },
    {"type": "content_block_stop", "index": 1},
    {
        "type": "message_delta",
        "delta": {"stop_reason": "tool_use", "stop_sequence": None},
        "usage": {"output_tokens": 64},
    },
    {"type": "message_stop"},
)


class Capture:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream", "request-id": "req_abc"},
            content=STREAM,
        )

    @property
    def body(self) -> dict[str, Any]:
        return dict(json.loads(self.requests[-1].content))


def _client(capture: Capture, **kwargs: Any) -> AnthropicModelClient:
    settings: dict[str, Any] = {
        "api_key": "test-key-not-real",
        "model": "claude-opus-5",
        "effort": "medium",
        "max_tokens": 6000,
    }
    settings.update(kwargs)
    return AnthropicModelClient(
        **settings, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(capture))
    )


async def _drain(stream: AsyncIterator[ModelEvent]) -> list[ModelEvent]:
    return [event async for event in stream]


def collect(client: Any, request: ModelRequest = REQUEST) -> list[ModelEvent]:
    return asyncio.run(_drain(client.stream(request)))


# ── the request ───────────────────────────────────────────────────────────────


def test_the_request_is_exactly_the_documented_configuration() -> None:
    capture = Capture()
    collect(_client(capture))

    sent = capture.requests[0]
    body = capture.body
    assert sent.url.path == "/v1/messages"
    assert sent.headers["anthropic-beta"] == FALLBACK_BETA
    assert body["stream"] is True
    assert body["model"] == "claude-opus-5"
    assert body["max_tokens"] == 6000
    assert body["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert body["output_config"] == {"effort": "medium"}
    assert body["tool_choice"] == {"type": "auto"}
    assert body["fallbacks"] == "default"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["messages"] == [dict(m) for m in REQUEST.messages]
    # Nothing else: no sampling parameters, no metadata, no server-side extras.
    assert set(body) == {
        "model",
        "max_tokens",
        "system",
        "messages",
        "tools",
        "tool_choice",
        "thinking",
        "output_config",
        "cache_control",
        "fallbacks",
        "stream",
    }


def test_the_cache_breakpoint_is_on_the_last_static_system_block() -> None:
    capture = Capture()
    collect(_client(capture))

    system = capture.body["system"]
    assert [block["text"] for block in system] == list(REQUEST.system)
    assert "cache_control" not in system[0]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}


def test_tools_are_strict_sorted_and_exactly_the_registry() -> None:
    capture = Capture()
    registry = load_all()
    collect(_client(capture), ModelRequest(system=["s"], messages=[], tools=registry.definitions()))

    tools = capture.body["tools"]
    assert [t["name"] for t in tools] == registry.names()
    assert all(t["strict"] is True for t in tools)
    assert all("eager_input_streaming" not in t for t in tools)
    # No server tools: every entry is a plain client tool with a schema, none has a `type`.
    assert all(set(t) == {"name", "description", "input_schema", "strict"} for t in tools)


def test_tools_are_sorted_even_when_given_out_of_order() -> None:
    capture = Capture()
    collect(_client(capture))

    assert [t["name"] for t in capture.body["tools"]] == ["accounts_list", "spend_by_category"]


def test_a_final_call_keeps_the_tools_but_may_not_call_one() -> None:
    capture = Capture()
    final = ModelRequest(
        system=REQUEST.system, messages=REQUEST.messages, tools=TOOLS, tools_enabled=False
    )
    collect(_client(capture), final)

    assert capture.body["tool_choice"] == {"type": "none"}
    assert [t["name"] for t in capture.body["tools"]] == ["accounts_list", "spend_by_category"]


def test_effort_and_model_come_from_configuration() -> None:
    capture = Capture()
    collect(_client(capture, model="claude-sonnet-5", effort="low", max_tokens=2000))

    assert capture.body["model"] == "claude-sonnet-5"
    assert capture.body["output_config"] == {"effort": "low"}
    assert capture.body["max_tokens"] == 2000


# ── the stream ────────────────────────────────────────────────────────────────


def test_the_stream_yields_text_then_complete_tool_calls_then_one_response() -> None:
    events = collect(_client(Capture()))

    assert events[:2] == [TextDelta("Let me "), TextDelta("check.")]
    assert events[2] == ToolUse(id="toolu_1", name="networth_get", input={"view": "mine"})
    final = events[-1]
    assert isinstance(final, ModelResponse)
    assert len(events) == 4
    assert final.stop_reason == "tool_use"
    assert final.model == "claude-opus-5"
    assert final.request_id == "req_abc"
    assert final.usage == Usage(
        input_tokens=120,
        cache_write_5m_tokens=900,
        cache_write_1h_tokens=0,
        cache_read_tokens=7300,
        output_tokens=64,
    )


def test_the_content_blocks_replay_as_request_blocks() -> None:
    final = collect(_client(Capture()))[-1]

    assert isinstance(final, ModelResponse)
    assert final.content == [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "toolu_1", "name": "networth_get", "input": {"view": "mine"}},
    ]


def test_only_opus_models_take_mid_conversation_system_messages() -> None:
    assert supports_system_messages("claude-opus-5")
    assert supports_system_messages("claude-opus-4-8")
    assert supports_system_messages("claude-opus-5-20260901")
    assert not supports_system_messages("claude-sonnet-5")
    assert not supports_system_messages("claude-haiku-4-5")


# ── the scripted client ───────────────────────────────────────────────────────


def test_the_scripted_client_replays_its_script_and_records_requests() -> None:
    seen: list[int] = []
    client = ScriptedModelClient(
        [
            ScriptedCall(
                text=["Checking."],
                tool_calls=[ToolUse("c1", "networth_get", {"view": "mine"})],
            ),
            ScriptedCall(
                text=["You have ", "$10.00 [c1.net_worth]."],
                usage=Usage(input_tokens=5, output_tokens=7),
                expect=lambda request: seen.append(len(request.messages)),
            ),
        ]
    )

    first = collect(client)
    second = collect(client, ModelRequest(system=["s"], messages=[{"role": "user"}] * 3, tools=[]))

    assert first[-1] == ModelResponse(
        stop_reason="tool_use",
        usage=Usage(input_tokens=1_000, output_tokens=100),
        model="scripted",
        request_id="scripted_1",
        content=[
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "c1", "name": "networth_get", "input": {"view": "mine"}},
        ],
    )
    assert [e for e in second if isinstance(e, TextDelta)] == [
        TextDelta("You have "),
        TextDelta("$10.00 [c1.net_worth]."),
    ]
    final = second[-1]
    assert isinstance(final, ModelResponse)
    assert final.stop_reason == "end_turn"
    assert seen == [3]
    assert len(client.requests) == 2
    assert client.exhausted


def test_the_scripted_client_refuses_to_improvise() -> None:
    client = ScriptedModelClient([])

    with pytest.raises(AssertionError, match="script has 0"):
        collect(client)


def test_the_scripted_client_can_fail_mid_answer() -> None:
    client = ScriptedModelClient([ScriptedCall(text=["Half an"], raises=ConnectionError("gone"))])
    received: list[ModelEvent] = []

    async def run() -> None:
        async for event in client.stream(REQUEST):
            received.append(event)

    with pytest.raises(ConnectionError):
        asyncio.run(run())
    assert received == [TextDelta("Half an")]


def test_an_expectation_failure_surfaces() -> None:
    def no_tools(request: ModelRequest) -> None:
        assert not request.tools, "tools were sent"

    client = ScriptedModelClient([ScriptedCall(text=["x"], expect=no_tools)])

    with pytest.raises(AssertionError, match="tools were sent"):
        collect(client)


# ── pricing ───────────────────────────────────────────────────────────────────


def test_every_token_class_is_priced_at_its_own_rate() -> None:
    """Opus 5, by hand: 1M of each class is $5 + $6.25 + $10 + $0.50 + $25 = $46.75."""
    usage = Usage(1_000_000, 1_000_000, 1_000_000, 1_000_000, 1_000_000)

    assert pricing.cost_cents(usage, "claude-opus-5", TODAY) == Decimal("4675")


@pytest.mark.parametrize(
    ("usage", "model", "cents"),
    [
        # 21,900 x $0.50 + 6,500 x $6.25 + 1,600 x $25 per MTok = $0.09157500
        (Usage(0, 6_500, 0, 21_900, 1_600), "claude-opus-5", Decimal("9.1575")),
        # Sonnet 5: 10,000 x $2 + 2,000 x $10 per MTok = $0.04
        (Usage(10_000, 0, 0, 0, 2_000), "claude-sonnet-5", Decimal("4")),
        # Haiku 4.5: 1,000 x $1 + 500 x $2 (1-hour write) per MTok = $0.002
        (Usage(1_000, 0, 500, 0, 0), "claude-haiku-4-5", Decimal("0.2")),
        # Opus 4.8 prices as Opus 5: 1 output token is 0.0025 cents.
        (Usage(0, 0, 0, 0, 1), "claude-opus-4-8", Decimal("0.0025")),
    ],
)
def test_cost_against_hand_computed_examples(usage: Usage, model: str, cents: Decimal) -> None:
    assert pricing.cost_cents(usage, model, TODAY) == cents


def test_cost_is_full_precision_and_rounded_once_for_display() -> None:
    one_token = pricing.cost_cents(Usage(output_tokens=1), "claude-opus-5", TODAY)
    thousand = sum((one_token for _ in range(1_000)), Decimal(0))

    assert one_token == Decimal("0.0025")
    assert pricing.display_cents(one_token) == 0
    assert pricing.display_cents(thousand) == 3  # 2.5 → 3, half up, once
    assert pricing.display_cents(Decimal("9.1575")) == 9


def test_an_unknown_model_costs_as_the_dearest_known_one() -> None:
    usage = Usage(1_000, 0, 0, 0, 1_000)

    assert pricing.cost_cents(usage, "claude-mystery-9", TODAY) == pricing.cost_cents(
        usage, "claude-opus-5", TODAY
    )
    assert not pricing.is_priced("claude-mystery-9")


def test_a_dated_snapshot_costs_as_its_alias() -> None:
    usage = Usage(1_000, 0, 0, 0, 1_000)

    assert pricing.cost_cents(usage, "claude-sonnet-5-20260801", TODAY) == pricing.cost_cents(
        usage, "claude-sonnet-5", TODAY
    )


def test_prices_are_effective_dated(monkeypatch: pytest.MonkeyPatch) -> None:
    old = pricing.PRICES["claude-sonnet-5"][0]
    raised = pricing.Price(
        dt.date(2027, 1, 1),
        Decimal(3),
        Decimal("3.75"),
        Decimal(6),
        Decimal("0.30"),
        Decimal(15),
    )
    monkeypatch.setitem(pricing.PRICES, "claude-sonnet-5", (old, raised))
    usage = Usage(output_tokens=1_000_000)

    assert pricing.cost_cents(usage, "claude-sonnet-5", dt.date(2026, 12, 31)) == Decimal(1000)
    assert pricing.cost_cents(usage, "claude-sonnet-5", dt.date(2027, 1, 1)) == Decimal(1500)


def test_scripted_and_local_calls_are_free() -> None:
    usage = Usage(1_000_000, 0, 0, 0, 1_000_000)

    assert pricing.cost_cents(usage, "scripted", TODAY, provider="scripted") == 0
    assert pricing.cost_cents(usage, "gpt-oss:20b", TODAY, provider="local") == 0


def test_the_configured_default_model_has_a_price() -> None:
    assert pricing.is_priced(Settings(database_url="postgresql://unused").advisor_model)


# ── settings ──────────────────────────────────────────────────────────────────


def _settings(**overrides: Any) -> Settings:
    return Settings(database_url="postgresql://unused", **overrides)


def test_the_advisor_is_off_by_default() -> None:
    settings = _settings()

    assert settings.advisor_enabled is False
    assert settings.advisor_active is False
    assert settings.advisor_model == "claude-opus-5"
    assert settings.advisor_effort == "medium"
    assert settings.advisor_max_tokens == 6000
    assert (
        settings.advisor_turn_cap_cents,
        settings.advisor_conversation_cap_cents,
        settings.advisor_monthly_cap_cents,
    ) == (50, 200, 2000)


@pytest.mark.parametrize(
    ("enabled", "key", "demo", "active"),
    [
        (True, "sk-test", False, True),
        (False, "sk-test", False, False),
        (True, None, False, False),
        (True, "", False, False),
        (True, "sk-test", True, False),
    ],
)
def test_active_needs_the_switch_a_key_and_not_the_demo(
    enabled: bool, key: str | None, demo: bool, active: bool
) -> None:
    settings = _settings(
        advisor_enabled=enabled,
        anthropic_api_key=SecretStr(key) if key is not None else None,
        demo_mode=demo,
    )

    assert settings.advisor_active is active


def test_the_key_never_prints() -> None:
    settings = _settings(anthropic_api_key=SecretStr("sk-test-secret"))

    assert "sk-test-secret" not in repr(settings)
    assert "sk-test-secret" not in str(settings.model_dump())
