"""Request middleware: logging context, and the demo's read-only lock.

One structured log line per request, carrying a request id that is also returned to
the caller so a user-visible error can be traced to a log entry without guessing.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

logger = get_logger("request")

#: Verbs that can change something. GET and HEAD cannot; OPTIONS is CORS preflight,
#: which this app does not use but which should not 405 if a browser sends one.
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject every mutating verb when `DEMO_MODE` is set.

    **This is not the demo boundary.** The boundary is that the demo deployment holds
    credentials for a different Neon project and therefore *cannot* reach the real
    database — see docs/adr/0003-demo-isolation.md. A flag in the application is one
    bad conditional away from being wrong, which is exactly why it is not being asked
    to carry the weight.

    What it is for is the demo's own data: it is public and unauthenticated, so
    without this anyone could rewrite the numbers everyone else sees. 405 with an
    `Allow` header rather than 403, because the resource is genuinely readable and it
    is the *method* that is not supported here.

    Enforced in middleware rather than per route so a route added later is covered by
    default. A demo lock that each new endpoint has to remember is not a lock.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Read per request, not at import. `scripts/export_openapi.py` imports this
        # app to build the contract and CI runs it with no environment at all, so
        # constructing Settings at import time breaks `make types` — which it did,
        # once. `get_settings` is cached, so this is one construction either way.
        if get_settings().demo_mode and request.method in MUTATING:
            return JSONResponse(
                {"detail": "This is a read-only demo. Sign-up and edits are disabled."},
                status_code=405,
                headers={"Allow": "GET, HEAD, OPTIONS"},
            )
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id, time the request, and emit exactly one log line."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Honour an inbound id so a request can be correlated across the proxy hop;
        # generate one otherwise.
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # One line, then re-raise so Sentry and Starlette still see it. Logging
            # here rather than in an exception handler is what keeps it to exactly
            # one line — a handler would log a second time for the 500 response.
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
