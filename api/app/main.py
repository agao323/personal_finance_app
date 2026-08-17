"""Application entrypoint.

No CORS middleware, deliberately. The browser never calls this service — it talks
only to the Next.js origin, which proxies over the private network. See
docs/ARCHITECTURE.md#request-path.
"""

from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine

app = FastAPI(title="Personal finance API")


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
