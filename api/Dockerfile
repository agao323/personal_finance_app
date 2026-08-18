# syntax=docker/dockerfile:1
#
# This image ships to Fly (ticket 008). The dev override in docker-compose.override.yml
# mounts source over it and swaps the command for --reload; it does not build a
# different image. Keep this deploy-ready.

# ── builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies resolve in their own layer, so editing application code doesn't
# reinstall the world. --frozen means uv.lock is authoritative and a stale lock
# fails the build rather than silently resolving something else.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# alembic/ and alembic.ini ship with the image because the Fly release command runs
# `alembic upgrade head` inside it. Without them the release command fails on the
# first deploy that has a migration to apply — which is every deploy after 009.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# Uses stdlib rather than adding curl to the image for one healthcheck.
HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=12 \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

# app/serve.py, not `uvicorn --host`. Neither 0.0.0.0 nor :: works on Fly — see
# that module's docstring. It binds one socket that accepts both families.
CMD ["python", "-m", "app.serve"]
