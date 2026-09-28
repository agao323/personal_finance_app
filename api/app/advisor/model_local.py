"""A free local model for development and evals: an OpenAI-compatible server on the laptop.

Ollama by default (`http://localhost:11434/v1`), serving an open-weight model — `gpt-oss:20b`
unless `LOCAL_MODEL` says otherwise. Building and evaluating the advisor costs nothing until
the owner switches production on (ticket 107); ADR 0009 has why production is not this.

**Translation, both ways.** Stored history is Anthropic-shaped content blocks — the production
provider's shape, replayed byte for byte — so this client translates on the way out and back:

- `tool_use` ↔ an assistant message's `tool_calls`; `tool_result` ↔ a `role: tool` message.
- Thinking blocks are the hosted model's and are dropped; the local model never sees them.
- Mid-conversation system messages are not sent: `supports_system_messages` is false for any
  local model, so the loop has already put the per-turn context in the user turn.

Text streams as it arrives. Tool calls stream in fragments and are returned only once complete;
arguments that are not valid JSON come back as the raw string, which the registry then refuses
as `invalid_args` — the same round trip a bad call from any model gets.

**Never on a deployment.** `Settings.advisor_provider_ready` is false for `local` wherever
`is_deployment` is true, and the API refuses to start configured that way.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx2

from app.advisor.model import (
    ModelEvent,
    ModelRequest,
    ModelResponse,
    TextDelta,
    ToolUse,
    Usage,
)

#: OpenAI `finish_reason` → the Anthropic `stop_reason` the loop understands.
_STOP_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}

#: A local model on a laptop can take a while to load and to think.
TIMEOUT = httpx2.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)


def _text(blocks: list[dict[str, Any]]) -> str:
    return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")


def to_chat_messages(request: ModelRequest) -> list[dict[str, Any]]:
    """Anthropic-shaped history as OpenAI chat messages."""
    messages: list[dict[str, Any]] = []
    if request.system:
        messages.append({"role": "system", "content": "\n\n".join(request.system)})
    for message in request.messages:
        role = message["role"]
        content = message["content"]
        blocks: list[dict[str, Any]] = (
            [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
        )
        if role == "assistant":
            calls = [
                {
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": block["input"]
                        if isinstance(block["input"], str)
                        else json.dumps(block["input"]),
                    },
                }
                for block in blocks
                if block.get("type") == "tool_use"
            ]
            out: dict[str, Any] = {"role": "assistant", "content": _text(blocks) or None}
            if calls:
                out["tool_calls"] = calls
            messages.append(out)
        elif role == "system":
            messages.append({"role": "system", "content": _text(blocks)})
        else:
            # Tool results must directly follow the assistant message that called them, so
            # they go first; any text in the same user message follows as its own message.
            for block in blocks:
                if block.get("type") == "tool_result":
                    result = block.get("content", "")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": result if isinstance(result, str) else json.dumps(result),
                        }
                    )
            text = _text(blocks)
            if text:
                messages.append({"role": "user", "content": text})
    return messages


def to_chat_tools(request: ModelRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in sorted(request.tools, key=lambda t: t.name)
    ]


def _parse_arguments(raw: str) -> Any:
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return raw  # the registry refuses a non-object as invalid_args


class LocalModelClient:
    provider = "local"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_tokens: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx2.AsyncClient(timeout=TIMEOUT)

    def build(self, request: ModelRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_chat_messages(request),
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        tools = to_chat_tools(request)
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto" if request.tools_enabled else "none"
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish: str | None = None
        usage = Usage()
        served = self.model
        request_id: str | None = None

        async with self._client.stream(
            "POST", f"{self._base_url}/chat/completions", json=self.build(request)
        ) as response:
            response.raise_for_status()
            request_id = response.headers.get("x-request-id")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                served = chunk.get("model") or served
                request_id = request_id or chunk.get("id")
                if chunk.get("usage"):
                    usage = Usage(
                        input_tokens=int(chunk["usage"].get("prompt_tokens") or 0),
                        output_tokens=int(chunk["usage"].get("completion_tokens") or 0),
                    )
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text_parts.append(delta["content"])
                        yield TextDelta(delta["content"])
                    for fragment in delta.get("tool_calls") or []:
                        call = calls.setdefault(
                            int(fragment.get("index", len(calls))),
                            {"id": "", "name": "", "arguments": ""},
                        )
                        function = fragment.get("function") or {}
                        call["id"] = fragment.get("id") or call["id"]
                        call["name"] += function.get("name") or ""
                        call["arguments"] += function.get("arguments") or ""
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]

        uses = [
            ToolUse(
                id=call["id"] or f"call_{index}",
                name=call["name"],
                input=_parse_arguments(call["arguments"]),
            )
            for index, call in sorted(calls.items())
        ]
        for use in uses:
            yield use
        content: list[dict[str, Any]] = []
        if text_parts:
            content.append({"type": "text", "text": "".join(text_parts)})
        content.extend(
            {"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses
        )
        stop = _STOP_REASONS.get(finish or "", "end_turn")
        if uses and stop == "end_turn":
            stop = "tool_use"  # some servers report "stop" alongside tool calls
        yield ModelResponse(
            stop_reason=stop,
            usage=usage,
            model=served,
            request_id=request_id,
            content=content,
        )
