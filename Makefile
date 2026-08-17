.DEFAULT_GOAL := help
.PHONY: help dev test test-api test-web lint lint-api lint-web format types seed migrate upgrade

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
dev: ## Start postgres + api + web in Docker with hot reload
	$(call not_yet,dev,002)

# ── Test ──────────────────────────────────────────────────────────────────────
test: test-api test-web ## Run both test suites

test-api:
	@# pytest exits 5 when it collects nothing. During scaffolding that is the
	@# expected state, not a failure. Once tests exist this passes through normally.
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
	$(call not_yet,types,005)

# ── Data ──────────────────────────────────────────────────────────────────────
seed: ## Load synthetic data into the local dev database
	$(call not_yet,seed,018)

migrate: ## Create a migration: make migrate m="add ownership stakes"
	$(call not_yet,migrate,009)

upgrade: ## Apply migrations up to head
	$(call not_yet,upgrade,009)
