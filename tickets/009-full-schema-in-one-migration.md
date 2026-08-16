# 009 — Full v1 schema in one reviewed migration
Status: todo
Wave: 1   Lane: —
Blocked by: 008
Read first: docs/ARCHITECTURE.md#data-model, docs/ARCHITECTURE.md#users-and-ownership

## Goal
Alembic is wired up and **one hand-reviewed migration** creates every v1 table. After this,
schema changes are incremental and serialised through a single lane — which is what makes
Wave 2's three parallel lanes safe.

## Acceptance criteria
- [ ] Alembic configured against the app's metadata; `make migrate` and `make upgrade` work
- [ ] The pytest fixture from 003 now runs `alembic upgrade head`. **No `metadata.create_all()` anywhere.**
- [ ] Tables: `users`, `credentials`, `institutions`, `accounts`, `ownership_stakes`, `balance_snapshots`, `categories`, `transactions`, `categorization_rules`, `import_mappings`, `data_marker`
- [ ] `accounts`: `kind`, `subtype`, `source`, `currency` with `CHECK (currency = 'USD')`, `institution_id`, `closed_at` nullable
- [ ] `ownership_stakes`: `account_id`, `owner_user_id` FK `users`, `percentage`, `effective_from`, `effective_to` nullable
- [ ] `balance_snapshots`: `account_id`, `as_of`, `balance`, `source`; unique on (`account_id`, `as_of`)
- [ ] `categories`: `parent_id` nullable for a two-level taxonomy, `kind` enum `income|expense|transfer`
- [ ] `transactions`: `external_id`, `account_id`, `posted_at`, `amount`, `merchant`, `description`, `category_id`, `category_source` enum `import|rule|manual`, `transfer_group_id` nullable
- [ ] Unique on (`account_id`, `external_id`) where `external_id` is not null
- [ ] All money columns `NUMERIC(19,2)`. No `Float` anywhere.
- [ ] Seed data in the migration: default categories across all three kinds; one `users` row from config; one `data_marker` row
- [ ] Migration hand-reviewed line by line, not blind autogenerate
- [ ] Tests: unit for every enum and CHECK constraint; functional asserting `upgrade → downgrade → upgrade` is clean

## Files
- `api/alembic.ini`
- `api/alembic/env.py`
- `api/alembic/versions/0001_initial.py`
- `api/app/models/*.py`
- `api/tests/test_schema.py`

## Notes
One migration for all of v1 is deliberate and is the reason Wave 2 can run in parallel:
Alembic's revision chain is linear and cannot absorb concurrent branches without a hand-merged
head. See DECISIONS.md.

`source` enum ships complete (`manual`, `csv`, `teller`, `plaid`, `simplefin`) even though only
the first two are implemented in v1, so adding a connector later needs no migration.

Liabilities are stored **positive** with `kind='liability'`. Net worth subtracts them.

This is a large migration but a mechanical one. If it starts to sprawl, split by table group
into `009a`/`009b` — but keep them in one lane and one PR so the head stays linear.
