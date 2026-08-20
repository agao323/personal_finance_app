"""Application entrypoint.

No CORS middleware, deliberately. The browser never calls this service — it talks
only to the Next.js origin, which proxies over the private network. See
docs/ARCHITECTURE.md#request-path.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import get_engine
from app.logging import configure_logging
from app.middleware import DemoReadOnlyMiddleware, RequestContextMiddleware
from app.observability import configure_sentry
from app.routers import (
    accounts,
    auth,
    categories,
    export,
    import_csv,
    net_worth,
    rules,
    runway,
    spend,
    transactions,
    users,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and Sentry once the process is actually starting.

    Deliberately not at import time: `scripts/export_openapi.py` imports this module
    to build the schema, and CI runs it with no DATABASE_URL. Reading settings on
    import would make the contract pipeline depend on a configured environment it
    has no reason to need.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_sentry(settings.sentry_dsn)

    # Refuse to serve a deployed environment with the session key that ships in the
    # repo. Anyone who has read the source could mint a cookie for any user id, and
    # nothing about the running app would look wrong — which is why this has to be a
    # failed boot rather than a warning in a log nobody reads.
    #
    # Keyed off `cookie_secure`, which is derived from WEB_ORIGIN: an https origin is
    # a deployment, and local dev on http://localhost keeps working untouched. One
    # signal rather than a second setting that could disagree with the first.
    if settings.cookie_secure and settings.session_secret_is_default:
        raise RuntimeError(
            "SESSION_SECRET is still the development default on an https origin. "
            "Set it before serving: fly secrets set -a pfa-api "
            'SESSION_SECRET="$(openssl rand -base64 32)"'
        )

    yield


app = FastAPI(title="Personal finance API", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(DemoReadOnlyMiddleware)

# The whole v1 surface, declared up front. Routes exist and return 501 until their
# lane implements them — that is what lets Wave 2's three lanes build against the same
# generated types without waiting on each other.
for _router in (
    net_worth.router,
    spend.router,
    runway.router,
    export.router,
    accounts.router,
    categories.router,
    import_csv.router,
    rules.router,
    transactions.router,
    auth.router,
    users.router,
):
    app.include_router(_router)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: bool


@app.get("/health")
def health() -> HealthResponse:
    """Liveness: the process is up and serving.

    Touches no database, by design. Fly probes this endpoint, and a check that fails
    on a transient database blip would have the platform restart instances that are
    perfectly healthy — turning a brief database problem into an outage.
    """
    return HealthResponse(status="ok")


@app.get("/ready", responses={503: {"model": ReadyResponse}})
def ready(response: Response) -> ReadyResponse:
    """Readiness: the database is reachable.

    Returns 503 rather than raising, so the body shape is the same either way and a
    caller can distinguish "unreachable" from "the API itself is broken".
    """
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return ReadyResponse(status="unavailable", database=False)
    return ReadyResponse(status="ok", database=True)
