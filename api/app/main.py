"""Application entrypoint.

This is a boot stub. Ticket 003 replaces it with structured settings, a SQLAlchemy
session dependency, and the real health endpoints. It exists now only because a
container needs something to serve and the Docker healthcheck needs something to
answer — see ``api/Dockerfile`` and ``docker-compose.yml``.
"""

from fastapi import FastAPI

app = FastAPI(title="Personal finance API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only: the process is up.

    Deliberately does not touch the database. Ticket 003 adds ``/ready`` for
    database reachability — a health check that fails on a transient database blip
    would have the platform restart a perfectly healthy process.
    """
    return {"status": "ok"}
