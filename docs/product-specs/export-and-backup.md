# Export and backup

The app must never become a place data can only go into — that is user-hostile, and it is
insurance against losing interest in the project.

## What you can do

- **Download everything** from the browser: `GET /export` returns every table as JSON.
- **Back up** from the command line: `make backup` writes `data/backups/pfa-<date>.json` on
  this machine and prints a row count per table.
- **Restore**: `make restore f=data/backups/pfa-<date>.json` loads an export into a database
  — the **local** one by default.

## Rules and edge cases

- **Every table, no exceptions.** A guard test fails when a table exists in the SQLAlchemy
  metadata and not in the export, so the next table added cannot silently fall out of it.
- **Money crosses as a string**, never a float, which would quietly round the balances the
  file exists to preserve.
- `make backup` **refuses to overwrite** a file from the same day (`ARGS=--force` to insist).
  It reads the **unpooled** Neon string from `BACKUP_DATABASE_URL` in `.env`, falling back to
  the local database, which is useful for rehearsing but is not a backup of anything.
- `make restore` **refuses a target that already has data** unless forced, and never
  defaults to production: overwriting a live database means naming it with `--database-url`
  *and* passing `--force`.
- **Restores parents before children**, ordered from `Base.metadata.sorted_tables`, and
  self-referencing categories roots first. The first drill found the export's field order
  put `ownership_stakes` before `users`.
- **No encryption on the file.** It never leaves a FileVault-encrypted disk; a second key to
  lose was the failure the previous design was rejected for.
- **No schedule.** A command that gets run beats a cron that silently stops.
- Do not open the export — it is the whole financial picture. The counts it prints are all a
  drill needs.

Why local, why no offsite copy, and what cannot be rebuilt:
[ADR 0008](../adr/0008-local-backups.md). The drill: [api/scripts/restore.md](../../api/scripts/restore.md).
Status: first drill passed on synthetic data; the production drill is pending (TD-003).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/export` | Every table, `Decimal` as strings, with `meta.counts` per table |

## Code

`api/app/routers/export.py` (queries directly — TD-001), `api/app/schemas/export.py`,
`api/scripts/export_local.py`, `api/scripts/restore_local.py`, `Makefile` (`backup`,
`restore`).

## Built by

017 (local exports and a restore actually performed; replaced the R2 design of ADR 0004).
