"""A turn's events as server-sent events: heartbeats in the gaps, and a stop when nobody listens.

docs/ADVISOR.md#request-path lists what sits between here and a phone — Cloudflare, Fly's
proxy, the Next.js route, undici — and each gives up on a quiet connection. So:

- Every event is one `data:` line of JSON. There is no `event:` line; `type` discriminates.
- A **heartbeat** goes out after 15 s of silence, which is shorter than every idle timeout on
  the path.
- The turn runs in **one task**, fed through a queue. The model stream's HTTP connection is
  opened and closed in that task, never handed between tasks, and the task can be cancelled
  cleanly.
- **A disconnect cancels the turn**: noticed between events by polling the request, and on a
  failed send by the server. Cancellation runs 097's path — the turn is marked `cancelled`,
  the model stream is closed, and the audit rows already written stay.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from app.schemas.advisor import HeartbeatEvent

HEARTBEAT_SECONDS = 15.0
#: How often a quiet stream checks whether the client is still there.
POLL_SECONDS = 1.0

HEADERS = {
    # `no-transform` keeps a compressing proxy from buffering the stream to gzip it.
    "Cache-Control": "no-cache, no-transform",
    # nginx and several CDNs buffer responses unless told not to.
    "X-Accel-Buffering": "no",
}

_END = object()


def encode(event: BaseModel) -> bytes:
    return f"data: {event.model_dump_json()}\n\n".encode()


async def stream_events(
    source: AsyncIterator[BaseModel],
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    poll_seconds: float = POLL_SECONDS,
) -> AsyncIterator[bytes]:
    """`source`'s events as SSE bytes, with heartbeats; cancels `source` if the client goes."""
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for event in source:
                queue.put_nowait(event)
        finally:
            queue.put_nowait(_END)

    task = asyncio.create_task(produce())
    loop = asyncio.get_running_loop()
    quiet_since = loop.time()
    try:
        while True:
            wait = min(poll_seconds, max(0.0, quiet_since + heartbeat_seconds - loop.time()))
            try:
                item = await asyncio.wait_for(queue.get(), wait)
            except TimeoutError:
                if is_disconnected is not None and await is_disconnected():
                    return
                if loop.time() - quiet_since >= heartbeat_seconds:
                    yield encode(HeartbeatEvent(type="heartbeat"))
                    quiet_since = loop.time()
                continue
            if item is _END:
                break
            assert isinstance(item, BaseModel)
            yield encode(item)
            quiet_since = loop.time()
        await task  # surfaces anything the turn raised
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def heartbeats(count: int, every: float) -> AsyncIterator[bytes]:
    """`count` heartbeats, `every` seconds apart, and nothing else. For `/stream-check`."""
    for index in range(count):
        if index:
            await asyncio.sleep(every)
        yield encode(HeartbeatEvent(type="heartbeat"))
