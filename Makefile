.DEFAULT_GOAL := help
.PHONY: help dev down logs smoke test test-api test-web guards lint lint-api lint-web format types types-check seed migrate upgrade

# Compose merges docker-compose.override.yml automatically. PROD_COMPOSE opts out,
# so smoke tests exercise the deploy-shaped images rather than the dev ones.
PROD_COMPOSE := docker compose -f docker-compose.yml

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
	@docker compose up --build

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
	@echo "── smoke passed ──"

# ── Test ──────────────────────────────────────────────────────────────────────
test: guards test-api test-web ## Run both test suites and the guard self-tests

guards: ## Run the architectural guards and their self-tests
	@./scripts/test_guards.sh
	@./scripts/check_no_float.sh
	@./scripts/check_no_public_api_url.sh

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

# ── Data ──────────────────────────────────────────────────────────────────────
seed: ## Load synthetic data into the local dev database
	$(call not_yet,seed,018)

migrate: ## Create a migration: make migrate m="add ownership stakes"
	$(call not_yet,migrate,009)

upgrade: ## Apply migrations up to head
	$(call not_yet,upgrade,009)
