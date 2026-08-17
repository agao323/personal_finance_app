"""Request-scoped logging context.

One structured line per request, carrying a request id that is also returned to the
caller so a user-visible error can be traced to a log entry without guessing.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

logger = get_logger("request")


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
