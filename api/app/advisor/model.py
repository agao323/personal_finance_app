"""The model client: one protocol, one provider, one fake.

The loop (097) sees only `ModelClient`. It sends a `ModelRequest` and reads back a stream of
`TextDelta` and `ToolUse` events ending in exactly one `ModelResponse`, which carries the
stop reason, token usage, the model that actually served (a refusal fallback may differ from
the one asked for), the request id, and the content blocks to replay next call.

`AnthropicModelClient` builds the request exactly as docs/ADVISOR.md#model-configuration
says. `ScriptedModelClient` replays a script and records every request, so the loop is
tested in CI with no network and no key.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx2
from anthropic import AsyncAnthropic

from app.advisor.tools import ToolDefinition

Effort = Literal["low", "medium", "high", "xhigh", "max"]

#: `fallbacks: "default"` re-routes a refusal to another Claude model inside the same call.
#: The scalar form needs this exact header; the array form's older header returns a 400.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: Models that accept `{"role": "system"}` in `messages` — the per-turn context and the
#: grounding retry use it. On any other model the loop prepends the context to the user
#: turn instead. Opus 4.8 is here because it is the default refusal fallback.
_SYSTEM_MESSAGE_MODELS = frozenset({"claude-opus-5", "claude-opus-4-8"})
_DATED = re.compile(r"-\d{8}$")


def supports_system_messages(model: str) -> bool:
    return _DATED.sub("", model) in _SYSTEM_MESSAGE_MODELS


@dataclass(frozen=True)
class ModelRequest:
    """One call's input. Built by the loop, identical in shape for every provider.

    `system` is the static system prompt, in blocks; the last is the cache breakpoint, so
    nothing that changes per turn may go in it. `messages` are content blocks exactly as
    stored — replayed byte for byte, or the cache after the first moved byte is lost.
    """

    system: Sequence[str]
    messages: Sequence[dict[str, Any]]
    tools: Sequence[ToolDefinition]
    #: False on a turn's last permitted call. The tools are still sent — they are the start
    #: of the cached prefix, and history holds tool calls that need their definitions — but
    #: the model may not call one.
    tools_enabled: bool = True


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolUse:
    """A complete tool call: emitted once its arguments have fully arrived."""

    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    """The end of one call. Always the last event, and always exactly one."""

    stop_reason: str | None
    usage: Usage
    model: str
    request_id: str | None
    content: list[dict[str, Any]]


ModelEvent = TextDelta | ToolUse | ModelResponse


class ModelClient(Protocol):
    #: `advisor_usage.provider` — decides whether a call is priced.
    provider: str
    #: The model asked for. The one that served is on `ModelResponse.model`.
    model: str

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...


# ── Anthropic ─────────────────────────────────────────────────────────────────


class AnthropicModelClient:
    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: Effort,
        max_tokens: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.effort: Effort = effort
        self.max_tokens = max_tokens
        # Two retries is the SDK default; set here so a change to it is a visible decision.
        self._client = AsyncAnthropic(api_key=api_key, http_client=http_client, max_retries=2)

    def build(self, request: ModelRequest) -> dict[str, Any]:
        """The keyword arguments for `beta.messages.stream`, and nothing else.

        What is **not** here matters as much: no `eager_input_streaming` (it turns off the
        API's own validation of tool input), no server tools (web search and fetch are
        egress), no sampling parameters, and `tool_choice` only ever `auto` or `none` — some
        newer models reject a forced choice.
        """
        system: list[dict[str, Any]] = [{"type": "text", "text": text} for text in request.system]
        if system:
            system[-1]["cache_control"] = {"type": "ephemeral"}
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "strict": True,
            }
            for tool in sorted(request.tools, key=lambda t: t.name)
        ]
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": list(request.messages),
            "tools": tools,
            "tool_choice": {"type": "auto" if request.tools_enabled else "none"},
            "thinking": {"type": "adaptive", "display": "omitted"},
            "output_config": {"effort": self.effort},
            # Top-level automatic caching: a breakpoint that follows the growing tail.
            "cache_control": {"type": "ephemeral"},
            "fallbacks": "default",
            "betas": [FALLBACK_BETA],
        }

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        # Leaving the `async with` — normally, by exception, or because the consumer closed
        # this generator when the browser went away — closes the HTTP response, which is
        # what stops the provider generating (and billing) further output.
        async with self._client.beta.messages.stream(**self.build(request)) as stream:
            async for event in stream:
                if event.type == "text":
                    yield TextDelta(event.text)
                elif event.type == "content_block_stop" and event.content_block.type == "tool_use":
                    block = event.content_block
                    yield ToolUse(id=block.id, name=block.name, input=block.input)
            final = await stream.get_final_message()
            request_id = stream.request_id
        usage = final.usage
        by_ttl = usage.cache_creation
        yield ModelResponse(
            stop_reason=final.stop_reason,
            usage=Usage(
                input_tokens=usage.input_tokens,
                cache_write_5m_tokens=by_ttl.ephemeral_5m_input_tokens if by_ttl else 0,
                cache_write_1h_tokens=by_ttl.ephemeral_1h_input_tokens if by_ttl else 0,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                output_tokens=usage.output_tokens,
            ),
            model=final.model,
            request_id=request_id,
            content=[block.model_dump(mode="json", exclude_none=True) for block in final.content],
        )


# ── Scripted ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScriptedCall:
    """One model call's scripted reply.

    `stop_reason` defaults to `tool_use` when there are tool calls and `end_turn` when
    there are none. `raises` is thrown after the text has streamed, to stand in for a
    connection dropped mid-answer. `expect` inspects the request that drew this reply.
    """

    text: Sequence[str] = ()
    tool_calls: Sequence[ToolUse] = ()
    stop_reason: str | None = None
    usage: Usage = Usage(input_tokens=1_000, output_tokens=100)
    model: str | None = None
    raises: Exception | None = None
    expect: Callable[[ModelRequest], None] | None = None


@dataclass
class ScriptedModelClient:
    script: Sequence[ScriptedCall]
    model: str = "scripted"
    provider: str = "scripted"
    requests: list[ModelRequest] = field(default_factory=list)

    @property
    def exhausted(self) -> bool:
        return len(self.requests) >= len(self.script)

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        if self.exhausted:
            raise AssertionError(
                f"model called {len(self.requests) + 1} times; script has {len(self.script)}"
            )
        call = self.script[len(self.requests)]
        self.requests.append(request)
        if call.expect is not None:
            call.expect(request)
        for chunk in call.text:
            yield TextDelta(chunk)
        if call.raises is not None:
            raise call.raises
        for tool_call in call.tool_calls:
            yield ToolUse(tool_call.id, tool_call.name, tool_call.input)
        content: list[dict[str, Any]] = []
        if call.text:
            content.append({"type": "text", "text": "".join(call.text)})
        content.extend(
            {"type": "tool_use", "id": t.id, "name": t.name, "input": t.input}
            for t in call.tool_calls
        )
        yield ModelResponse(
            stop_reason=call.stop_reason or ("tool_use" if call.tool_calls else "end_turn"),
            usage=call.usage,
            model=call.model or self.model,
            request_id=f"scripted_{len(self.requests)}",
            content=content,
        )
