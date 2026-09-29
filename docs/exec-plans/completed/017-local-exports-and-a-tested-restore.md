# 017 — Local exports, and a restore actually performed
Status: done
Wave: 2   Lane: A
Blocked by: none
Read first: docs/adr/0008-local-backups.md

## Goal
`make backup` writes the whole database to a JSON file on this machine, `make restore`
reads one back, and the restore has been run once for real. **This ticket gates real data
entering production** — that part has not changed.

## Acceptance criteria
- [x] `GET /export` covers **every table**. It currently misses `institutions`,
      `card_perks`, `perk_redemptions` and `import_mappings` — it was written before the
      cards feature and nobody extended it, while the ticket claimed "the full dataset".
- [x] A guard test fails when a table exists in `Base.metadata` and not in the export, so
      the next table added cannot silently fall out of it.
- [x] `make backup` writes `data/backups/pfa-<date>.json`, reading the database URL from
      `.env`. `data/` is gitignored and stays that way.
- [x] It refuses to overwrite an existing file for the same day, and says what it wrote:
      path, size, and a row count per table.
- [x] `make restore f=<file>` loads an export into a database named by `.env`, refusing
      outright unless the target is empty or `--force` is given. **The production database
      is never the default target.**
- [x] A restore performed for real into the local Docker database, row counts compared, and
      the drill recorded in the table in ADR 0008.
- [x] No encryption on the export. FileVault protects the disk and the file never leaves
      it; a second key to lose is the failure ADR 0004 was rejected for.
- [x] `api/scripts/backup.py`, `api/tests/test_backup.py`, `.github/workflows/backup.yml`
      and the old `api/scripts/restore.md` are deleted, not left to rot.
- [x] `boto3` and `cryptography` come out of the dependencies if nothing else uses them.
- [x] `make types` run if the export response model changed.
- [x] Tests: unit — the export covers every mapped table (the guard above); round-trip of
      a synthetic dataset through export and restore with identical row counts and a
      spot-checked `Decimal`. Functional — `/export` against the synthetic seed includes a
      card, a perk, and a redemption.

## Files
- `api/app/routers/export.py`, `api/app/schemas/export.py`
- `api/scripts/export_local.py`, `api/scripts/restore_local.py` (new)
- `api/scripts/restore.md` (rewritten)
- `Makefile`
- `api/tests/test_export.py`
- deletions: `api/scripts/backup.py`, `api/tests/test_backup.py`,
  `.github/workflows/backup.yml`

## Notes
This replaces the R2 design wholesale. [ADR 0008](../../adr/0008-local-backups.md) has
the reasoning; the short version is that the old design put the encryption key in GitHub
Actions secrets next to the R2 credentials and the database URL, which concentrates
precisely what it claimed to separate, and that the data being protected is mostly
reconstructible anyway.

**Only `balance_snapshots` is genuinely irreplaceable.** Banks do not serve historical
balance-at-a-date, and for 401k, HSA, brokerage, property and vehicle values nobody does.
`perk_redemptions` is also unreconstructable and trivial. Everything else is bank CSVs
inside their retention window, or a handful of hand-typed rows. That is the whole reason
this ticket got smaller.

**The tested restore is still the acceptance criterion, not the backup command.** An
export nobody has ever read back is a file you believe in. It is much cheaper to prove
now: load a JSON file into the local Docker database and compare counts.

The export is JSON with `Decimal` as strings, which `routers/export.py` already does and
explains — a float would quietly round the balances the file exists to preserve.

**No schedule.** A command that gets run beats a cron that silently stops, which is the
lesson the old design taught over five weeks of failing every night. Revisit a launchd
job once the habit exists.

## Done — 2026-09-27

The drill found a real bug on its first run, which is the argument for drills. The restore
walked `EXPORTED` — the response contract's field order — which puts `ownership_stakes`
before `users`, and the foreign key refused. Order now comes from
`Base.metadata.sorted_tables`, derived from the same metadata Alembic autogenerates against,
so it cannot fall out of step with the schema. A test pins it.

A second ordering problem behind it: `categories` references itself through `parent_id`, so
table ordering is not enough — the rows inside one insert need parents first too. Handled one
level deep, which is what this schema has, and said so rather than inventing a topological
sort for a shape that does not exist.

The full round-trip is the documented drill rather than a unit test: `restore()` opens its own
connection, so running it inside the suite's per-test transaction would either break isolation
or test something other than what runs. The ordering — where both bugs were — is unit-tested.

Recorded in the drills table in [ADR 0008](../../adr/0008-local-backups.md). Counts matched
across all twelve tables and the Decimal sums matched exactly.
