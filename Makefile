.DEFAULT_GOAL := help
.PHONY: help dev advisor-local down logs smoke deploy-api deploy-web test test-api test-web e2e guards lint lint-api lint-web format types types-check seed migrate upgrade backup restore eval eval-label eval-examples eval-fixtures advisor-purge deploy-demo

# Compose merges docker-compose.override.yml automatically. PROD_COMPOSE opts out,
# so smoke tests exercise the deploy-shaped images rather than the dev ones.
PROD_COMPOSE := docker compose -f docker-compose.yml

# Alembic runs on the host, so it needs localhost rather than the compose service
# name the API container uses.
LOCAL_DB_URL := postgresql+psycopg://pfa:pfa_local_dev@localhost:5432/pfa

# The same database seen from inside a compose container, where the host is the
# service name rather than localhost.
COMPOSE_DB_URL := postgresql+psycopg://pfa:pfa_local_dev@postgres:5432/pfa

# Stub targets fail loudly rather than silently doing nothing — a no-op target is
# indistinguishable from a passing one, and that hides an unimplemented ticket.
define not_yet
	@echo "make $(1) is not implemented yet — ticket $(2)." >&2
	@exit 1
endef

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ── Run ───────────────────────────────────────────────────────────────────────
.env:
	@cp .env.example .env
	@echo "Created .env from .env.example. Local dev credentials only — edit if you like."

dev: .env ## Start postgres + api + web in Docker with hot reload
	@# Hot reload covers edits to existing files. A brand new route *directory*
	@# under web/src/app is often missed by the dev server's watcher through the
	@# bind mount, and the route 404s until `docker compose restart web`.
	@docker compose up --build

LOCAL_MODEL_NAME := $(or $(model),gpt-oss:20b)

advisor-local: .env ## Start the stack with the advisor on a free local model (Ollama): model=
	@# The model runs on this Mac, outside Docker, so it can use the GPU. The download is
	@# about 13 GB and is yours to start; this only checks it is there.
	@if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then \
		echo "No local model server answering on localhost:11434. To set one up:"; \
		echo "  1. Install Ollama:  brew install ollama   (or https://ollama.com/download)"; \
		echo "  2. Start it:        ollama serve"; \
		echo "  3. Pull the model:  ollama pull $(LOCAL_MODEL_NAME)   # about 13 GB"; \
		exit 1; \
	fi
	@if ! curl -fsS http://localhost:11434/api/tags | grep -q '"$(LOCAL_MODEL_NAME)"'; then \
		echo "The model server is up but $(LOCAL_MODEL_NAME) is not pulled:"; \
		echo "  ollama pull $(LOCAL_MODEL_NAME)   # about 13 GB"; \
		exit 1; \
	fi
	@echo "Local model $(LOCAL_MODEL_NAME) is ready. Starting the stack with the advisor on it."
	@ADVISOR_ENABLED=true ADVISOR_PROVIDER=local LOCAL_MODEL=$(LOCAL_MODEL_NAME) docker compose up --build

down: ## Stop everything (add v=1 to also drop the database volume)
	@docker compose down $(if $(v),--volumes,)

logs: ## Tail logs from all services
	@docker compose logs -f

smoke: .env ## Bring up the deploy-shaped stack and assert it actually works
	@echo "── building and starting (deploy images, no dev override) ──"
	@$(PROD_COMPOSE) up -d --build --wait
	@echo "── all three healthy ──"
	@$(PROD_COMPOSE) ps --format '  {{.Service}}\t{{.Status}}'
	@echo "── api must NOT be published to the host ──"
	@# A published port renders as "0.0.0.0:3000->3000/tcp"; an internal-only one as
	@# bare "8000/tcp". Testing for the arrow is the reliable check — `compose port`
	@# prints "invalid IP:0" rather than nothing when there is no mapping.
	@if $(PROD_COMPOSE) ps --format '{{.Service}} {{.Ports}}' | grep '^api ' | grep -q -- '->'; then \
		echo "  FAIL: api is published to the host; it must only exist on the internal network" >&2; \
		exit 1; \
	fi
	@echo "  ok: no host mapping for api:8000"
	@echo "── web serves on the host ──"
	@curl -fsS -o /dev/null -w '  ok: http %{http_code} from localhost:$(or $(WEB_PORT),3000)\n' \
		"http://localhost:$(or $(WEB_PORT),3000)/"
	@echo "── web container reaches api over the internal network ──"
	@$(PROD_COMPOSE) exec -T web wget -qO- http://api:8000/health \
		| grep -q '"ok"' && echo "  ok: api /health answered from inside web" \
		|| (echo "  FAIL: web cannot reach api" >&2; exit 1)
	@echo "── the full browser path: host → web → proxy → api → postgres ──"
	@curl -fsS "http://localhost:$(or $(WEB_PORT),3000)/api/ready" \
		| grep -q '"database":true' \
		&& echo "  ok: /api/ready reports the database reachable" \
		|| (echo "  FAIL: proxy did not reach the API, or the database is down" >&2; exit 1)
	@echo "── proxy passes upstream status through ──"
	@test "$$(curl -s -o /dev/null -w '%{http_code}' \
		"http://localhost:$(or $(WEB_PORT),3000)/api/nope")" = "404" \
		&& echo "  ok: unknown route proxies back a 404, not a 200 or a 502" \
		|| (echo "  FAIL: proxy masked the upstream status" >&2; exit 1)
	@echo "── migrations, as the Fly release command runs them ──"
	@$(PROD_COMPOSE) exec -T api alembic upgrade head >/dev/null \
		&& echo "  ok: alembic upgrade head" \
		|| (echo "  FAIL: migrations did not apply" >&2; exit 1)
	@echo "── server-sent events cross the proxy unbuffered ──"
	@python3 scripts/check_stream_timing.py \
		"http://localhost:$(or $(WEB_PORT),3000)/api/advisor/stream-check"
	@echo "── smoke passed ──"

# ── Test ──────────────────────────────────────────────────────────────────────
test: guards test-api test-web ## Run both test suites and the guard self-tests

guards: ## Run the architectural guards and their self-tests
	@./scripts/test_guards.sh
	@./scripts/check_no_float.sh
	@./scripts/check_no_public_api_url.sh
	@./scripts/check_fly_api_private.sh
	@./scripts/check_fly_api_private.sh fly.demo-api.toml
	@./scripts/check_no_model_key_outside_api.sh

test-api: .env
	@# The suite runs against real Postgres, not SQLite — see api/tests/conftest.py.
	@# Idempotent and fast when it is already up. CI supplies its own service
	@# container, so it must not start a second one.
	@if [ -z "$$CI" ]; then docker compose up -d --wait postgres >/dev/null; fi
	@# pytest exits 5 when it collects nothing, which was the expected state during
	@# scaffolding. Kept so an empty suite is never mistaken for a failure.
	@cd api && uv run pytest; status=$$?; [ $$status -eq 0 ] || [ $$status -eq 5 ]

test-web:
	@cd web && pnpm test

e2e: .env ## Run the Playwright smoke tests against the deploy-shaped stack
	@# PROD_COMPOSE, not the dev override: end-to-end tests should exercise the images
	@# that actually deploy, which is the same call `smoke` makes. It is also more
	@# reliable — no bind mount, so the container's node_modules cannot be confused
	@# with the host's.
	@#
	@# Seeded first, and deliberately: these assert against real figures, and a
	@# half-empty database fails them for a reason that is not a bug. The seed also
	@# clears registered passkeys, which is what lets the run register a fresh one.
	@$(PROD_COMPOSE) up -d --build --wait postgres api web >/dev/null
	@# Explicitly, because the deploy-shaped stack deliberately has no migration step:
	@# on Fly that is the release command, and compose has no equivalent. The dev
	@# override runs it inside the API's command instead, which is why this was
	@# invisible until e2e moved off the dev stack.
	@$(PROD_COMPOSE) exec -T -e ALEMBIC_DATABASE_URL=$(COMPOSE_DB_URL) \
		api alembic upgrade head >/dev/null
	@$(PROD_COMPOSE) exec -T -e DATABASE_URL=$(COMPOSE_DB_URL) \
		api python scripts/seed_synthetic.py >/dev/null
	@cd web && pnpm exec playwright test

# ── Lint ──────────────────────────────────────────────────────────────────────
lint: lint-api lint-web ## ruff + mypy + eslint + tsc + prettier

lint-api:
	@cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy .

lint-web:
	@cd web && pnpm lint && pnpm typecheck && pnpm format:check

format: ## Autoformat both sides
	@cd api && uv run ruff format . && uv run ruff check --fix .
	@cd web && pnpm format

# ── Contract ──────────────────────────────────────────────────────────────────
types: ## Regenerate web/src/lib/api-types.ts from the API's OpenAPI schema
	@cd api && uv run python scripts/export_openapi.py >/dev/null
	@cd web && pnpm exec openapi-typescript ../api/openapi.json -o src/lib/api-types.ts
	@cd web && pnpm exec prettier --write --ignore-path /dev/null src/lib/api-types.ts >/dev/null
	@echo "web/src/lib/api-types.ts regenerated — commit it."

types-check: types ## Fail if the committed types drift from the Pydantic models
	@if ! git diff --quiet -- web/src/lib/api-types.ts; then \
		echo ""; \
		echo "  web/src/lib/api-types.ts is out of date with the API's response models." >&2; \
		echo "  Run 'make types' and commit the result." >&2; \
		echo ""; \
		git --no-pager diff --stat -- web/src/lib/api-types.ts >&2; \
		exit 1; \
	fi
	@echo "contract is in sync"

# ── Deploy ────────────────────────────────────────────────────────────────────
# The directory argument sets the Docker build context. Without it flyctl looks for
# a Dockerfile at the repo root and uploads the whole tree, node_modules included.
# -c takes an absolute path because flyctl resolves a relative one against that same
# directory argument, not the shell's cwd.
deploy-api: ## Deploy the API to Fly (runs migrations as a release command)
	@fly deploy ./api -c $(CURDIR)/fly.api.toml

deploy-web: ## Deploy the web app to Fly
	@fly deploy ./web -c $(CURDIR)/fly.web.toml

deploy-demo: ## Deploy both demo apps (separate Neon project — see ADR 0003)
	@fly deploy ./api -c $(CURDIR)/fly.demo-api.toml
	@fly deploy ./web -c $(CURDIR)/fly.demo-web.toml --build-arg NEXT_PUBLIC_DEMO=true

# ── Data ──────────────────────────────────────────────────────────────────────
seed: .env ## Load synthetic data into the local dev database
	@docker compose up -d --wait postgres >/dev/null
	@cd api && DATABASE_URL="$(LOCAL_DB_URL)" uv run python scripts/seed_synthetic.py
	@echo "Refuses to run against a database whose data_marker says the data is real."

migrate: .env ## Create a migration: make migrate m="add ownership stakes"
	@test -n "$(m)" || (echo 'usage: make migrate m="what it does"' >&2; exit 1)
	@docker compose up -d --wait postgres >/dev/null
	@# --autogenerate proposes; a human reviews. Never commit one unread.
	@cd api && ALEMBIC_DATABASE_URL="$(LOCAL_DB_URL)" \
		uv run alembic revision --autogenerate -m "$(m)"
	@echo ""
	@echo "Review it line by line before committing. Autogenerate misses CHECK"
	@echo "constraints, partial indexes, enum value changes, and every data migration."

upgrade: .env ## Apply migrations up to head
	@docker compose up -d --wait postgres >/dev/null
	@cd api && ALEMBIC_DATABASE_URL="$(LOCAL_DB_URL)" uv run alembic upgrade head

backup: .env ## Write the whole database to data/backups/ on this machine (ADR 0008)
	@# Reads BACKUP_DATABASE_URL from .env — the production Neon string. Falls back to the
	@# local database, which is useful for rehearsing but is not a backup of anything.
	@cd api && uv run python scripts/export_local.py $(ARGS)

restore: .env ## Load an export back: make restore f=data/backups/pfa-2026-09-27.json
	@test -n "$(f)" || (echo 'usage: make restore f=data/backups/pfa-YYYY-MM-DD.json' >&2; exit 1)
	@# Defaults to the LOCAL database, never production. Restoring over the real one is a
	@# deliberate act that has to name its own --database-url.
	@cd api && DATABASE_URL="$(LOCAL_DB_URL)" uv run python scripts/restore_local.py "$(CURDIR)/$(f)" $(ARGS)

eval-fixtures: .env ## Recompute api/evals/expected.json from the eval world (no model; rolled back)
	@docker compose up -d --wait postgres >/dev/null
	@# Builds the eval world inside a transaction in pfa_eval (created and migrated if need be)
	@# and rolls it back. The development database is never touched.
	@cd api && uv run python -m evals.fixtures

eval: .env ## Ask the golden questions of a model and grade them: provider=local|anthropic n= only= max_cost=
	@# provider=anthropic spends real money on the pfa-eval workspace's key
	@# (EVAL_ANTHROPIC_API_KEY), never the production one. Never run in CI.
	@docker compose up -d --wait postgres >/dev/null
	@cd api && uv run python -m evals.run --provider $(or $(provider),local) --n $(or $(n),1) \
		--max-cost $(or $(max_cost),10) $(if $(only),--only $(only))

eval-label: ## Mark recorded advice answers pass or fail, to calibrate the rubric grader
	@cd api && uv run python -m evals.label

eval-examples: ## Export chosen eval transcripts for the demo (review the diff before committing)
	@cd api && uv run python -m evals.examples

advisor-purge: .env ## Delete advisor transcripts, audit and usage rows past retention
	@# The LOCAL database, like seed and restore. Production purges itself at the start
	@# of every advisor request, so it never needs this.
	@cd api && DATABASE_URL="$(LOCAL_DB_URL)" uv run python scripts/advisor_purge.py

downgrade: .env ## Roll back one migration
	@cd api && ALEMBIC_DATABASE_URL="$(LOCAL_DB_URL)" uv run alembic downgrade -1
