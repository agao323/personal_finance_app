"""The local model adapter: translation both ways, against recorded chat-completions streams.

No network: an `httpx2.MockTransport` answers with the chunks an OpenAI-compatible server (Ollama)
sends. And the one rule that matters most here — the local provider is refused on a deployment.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.advisor.model import ModelEvent, ModelRequest, ModelResponse, TextDelta, ToolUse, Usage
from app.advisor.model_local import LocalModelClient, to_chat_messages
from app.advisor.pricing import cost_cents
from app.advisor.tools import ToolContext, ToolDefinition, load_all, savepoint_read_only
from app.config import Settings, get_settings
from app.schemas.common import ViewScope

TOOLS = [
    ToolDefinition("spend_by_category", "Spending.", {"type": "object", "properties": {}}),
    ToolDefinition("networth_get", "Net worth.", {"type": "object", "properties": {}}),
]


def _sse(*chunks: dict[str, Any]) -> bytes:
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return (body + "data: [DONE]\n\n").encode()


def _chunk(delta: dict[str, Any], finish: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "model": "gpt-oss:20b",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        **extra,
    }


#: Text, then two tool calls streamed in fragments and interleaved, then usage.
PARALLEL = _sse(
    _chunk({"role": "assistant", "content": "Let me "}),
    _chunk({"content": "check."}),
    _chunk(
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "networth_get", "arguments": ""},
                }
            ]
        }
    ),
    _chunk(
        {
            "tool_calls": [
                {
                    "index": 1,
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "spend_by", "arguments": '{"period"'},
                }
            ]
        }
    ),
    _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"view": "mine"}'}}]}),
    _chunk(
        {
            "tool_calls": [
                {
                    "index": 1,
                    "function": {"name": "_category", "arguments": ': {"preset": "last_month"}}'},
                }
            ]
        }
    ),
    _chunk({}, "tool_calls"),
    {
        "id": "chatcmpl-1",
        "model": "gpt-oss:20b",
        "choices": [],
        "usage": {"prompt_tokens": 812, "completion_tokens": 64},
    },
)


class Capture:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=self.body
        )

    @property
    def sent(self) -> dict[str, Any]:
        return dict(json.loads(self.requests[-1].content))


def _client(capture: Capture) -> LocalModelClient:
    return LocalModelClient(
        base_url="http://localhost:11434/v1/",
        model="gpt-oss:20b",
        max_tokens=6000,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(capture)),
    )


async def _drain(stream: AsyncIterator[ModelEvent]) -> list[ModelEvent]:
    return [event async for event in stream]


def collect(client: LocalModelClient, request: ModelRequest) -> list[ModelEvent]:
    return asyncio.run(_drain(client.stream(request)))


HISTORY = ModelRequest(
    system=["You are the advisor.", "Tool guidance."],
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Today is Sunday 2026-09-27."},
                {"type": "text", "text": "Net worth?"},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "Checking."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "networth_get",
                    "input": {"view": "mine"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"call":"c1"}'},
                {"type": "text", "text": "No more lookups."},
            ],
        },
    ],
    tools=TOOLS,
)


# ── the request ───────────────────────────────────────────────────────────────


def test_history_translates_to_chat_messages() -> None:
    assert to_chat_messages(HISTORY) == [
        {"role": "system", "content": "You are the advisor.\n\nTool guidance."},
        {"role": "user", "content": "Today is Sunday 2026-09-27.Net worth?"},
        {
            "role": "assistant",
            "content": "Checking.",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {"name": "networth_get", "arguments": '{"view": "mine"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "content": '{"call":"c1"}'},
        {"role": "user", "content": "No more lookups."},
    ]


def test_the_request_streams_with_sorted_tools_and_usage() -> None:
    capture = Capture(_sse(_chunk({"content": "Hi."}, "stop")))
    collect(_client(capture), HISTORY)

    sent = capture.sent
    assert capture.requests[0].url == "http://localhost:11434/v1/chat/completions"
    assert sent["model"] == "gpt-oss:20b"
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert sent["max_tokens"] == 6000
    assert [t["function"]["name"] for t in sent["tools"]] == ["networth_get", "spend_by_category"]
    assert sent["tools"][0]["type"] == "function"
    assert sent["tool_choice"] == "auto"


def test_a_final_call_sends_the_tools_but_forbids_them() -> None:
    capture = Capture(_sse(_chunk({"content": "Done."}, "stop")))
    final = ModelRequest(system=["s"], messages=HISTORY.messages, tools=TOOLS, tools_enabled=False)
    collect(_client(capture), final)

    assert capture.sent["tool_choice"] == "none"


# ── the response ──────────────────────────────────────────────────────────────


def test_text_streams_and_parallel_tool_calls_come_back_whole() -> None:
    events = collect(_client(Capture(PARALLEL)), HISTORY)

    assert events[:2] == [TextDelta("Let me "), TextDelta("check.")]
    assert events[2:4] == [
        ToolUse(id="call_a", name="networth_get", input={"view": "mine"}),
        ToolUse(id="call_b", name="spend_by_category", input={"period": {"preset": "last_month"}}),
    ]
    final = events[-1]
    assert isinstance(final, ModelResponse)
    assert final.stop_reason == "tool_use"
    assert final.usage == Usage(input_tokens=812, output_tokens=64)
    assert final.model == "gpt-oss:20b"
    assert final.content == [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "call_a", "name": "networth_get", "input": {"view": "mine"}},
        {
            "type": "tool_use",
            "id": "call_b",
            "name": "spend_by_category",
            "input": {"period": {"preset": "last_month"}},
        },
    ]


@pytest.mark.parametrize(
    ("finish", "stop"),
    [
        ("stop", "end_turn"),
        ("length", "max_tokens"),
        ("content_filter", "refusal"),
        (None, "end_turn"),
    ],
)
def test_finish_reasons_map_to_stop_reasons(finish: str | None, stop: str) -> None:
    events = collect(_client(Capture(_sse(_chunk({"content": "x"}, finish)))), HISTORY)

    final = events[-1]
    assert isinstance(final, ModelResponse) and final.stop_reason == stop


def test_a_malformed_tool_call_comes_back_as_invalid_args(db_session: Session) -> None:
    body = _sse(
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_x",
                        "function": {"name": "networth_get", "arguments": '{"view": mine'},
                    }
                ]
            },
            "tool_calls",
        )
    )
    (use,) = [e for e in collect(_client(Capture(body)), HISTORY) if isinstance(e, ToolUse)]
    assert use.input == '{"view": mine'

    ctx = ToolContext(
        today=dt.date(2026, 9, 27),
        user_id=1,
        view=ViewScope.MINE,
        sessions=savepoint_read_only(db_session),
    )
    outcome = load_all().run(use.name, use.input, ctx)

    assert outcome.status == "invalid_args"


def test_local_calls_are_priced_at_zero() -> None:
    assert (
        cost_cents(Usage(10**6, 0, 0, 0, 10**6), "gpt-oss:20b", dt.date(2026, 9, 27), "local") == 0
    )


def test_a_local_model_reads_the_context_in_the_user_turn() -> None:
    from app.advisor.model import supports_system_messages

    assert not supports_system_messages("gpt-oss:20b")
    assert not supports_system_messages("qwen3:30b-a3b")


# ── never on a deployment ─────────────────────────────────────────────────────


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": "postgresql://unused", "advisor_enabled": True}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_the_local_provider_is_ready_on_a_laptop_only() -> None:
    laptop = _settings(advisor_provider="local", web_origin="http://localhost:3000")
    deployed = _settings(advisor_provider="local", web_origin="https://allofmymoney.com")

    assert laptop.advisor_active is True
    assert deployed.advisor_provider_ready is False
    assert deployed.advisor_active is False


def test_the_scripted_provider_is_never_configured() -> None:
    assert _settings(advisor_provider="scripted").advisor_active is False


def test_a_deployment_configured_for_the_local_model_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "allofmymoney.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-123")
    monkeypatch.setenv("ADVISOR_PROVIDER", "local")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ADVISOR_PROVIDER=local"), TestClient(app):
            pass
    finally:
        get_settings.cache_clear()


def test_the_route_will_not_build_a_local_client_on_a_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers.advisor import advisor_client

    monkeypatch.setenv("ADVISOR_PROVIDER", "local")
    monkeypatch.setenv("ADVISOR_ENABLED", "true")
    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    get_settings.cache_clear()
    try:
        assert advisor_client() is None
    finally:
        get_settings.cache_clear()
    monkeypatch.setenv("WEB_ORIGIN", "http://localhost:3000")
    get_settings.cache_clear()
    try:
        client = advisor_client()
        assert isinstance(client, LocalModelClient) and client.model == "gpt-oss:20b"
    finally:
        get_settings.cache_clear()
