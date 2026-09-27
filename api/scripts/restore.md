# Backing up, and restoring

Written to be runnable by someone who did not write it, on the worst day. Every command is
literal.

The design and its reasoning are in [ADR 0008](../../docs/adr/0008-local-backups.md). The
short version: Neon's own point-in-time recovery is layer one, a JSON file on this machine
is layer two, and nothing we operate keeps a copy anywhere else.

**An untested export is not a backup.** Run the drill below at least once before the
database holds anything you would miss, and again after any change to these scripts.

## What you need

| | Where it lives |
|---|---|
| `BACKUP_DATABASE_URL` | Documented in `.env.example`, but `make backup` does not read `.env` yet (TD-016 in `docs/exec-plans/tech-debt-tracker.md`): give it at the prompt in going-live §C2. The **unpooled** Neon connection string — copy it from the Neon console. |
| Docker running | Only for the restore drill, which uses the local database. |

There is no encryption key. That is deliberate: the file never leaves a FileVault-encrypted
disk, and a second key to lose was the failure the previous design was rejected for.

## Taking a backup

```bash
make backup
```

Writes `data/backups/pfa-<today>.json` and prints a row count per table. `data/` is
gitignored and always has been. Whatever backs up this machine carries the file from there.

It refuses to overwrite a file from the same day. Pass `ARGS=--force` if you mean to.

Run it before and after anything significant: a bulk import, a schema migration, deleting an
account.

## The restore drill

The point is to prove the file reads back, not that it was written. Do this into a scratch
database, never production.

**1. Make a scratch database and migrate it.**

```bash
docker compose exec postgres psql -U pfa -d pfa -c "CREATE DATABASE pfa_restore_drill;"
```

```bash
cd api && ALEMBIC_DATABASE_URL="postgresql+psycopg://pfa:pfa_local_dev@localhost:5432/pfa_restore_drill" uv run alembic upgrade head
```

**2. Load the export into it.**

```bash
cd api && uv run python scripts/restore_local.py ../data/backups/pfa-2026-09-27.json --database-url "postgresql://pfa:pfa_local_dev@localhost:5432/pfa_restore_drill" --force
```

It prints a row count per table. Compare them against the `meta.counts` block in the file.

**3. Check the numbers, not just the counts.**

Counts match when the rows are all there. Sums match when the *values* are too, which is what
you actually care about.

```bash
docker compose exec postgres psql -U pfa -d pfa_restore_drill -c "SELECT count(*), sum(balance) FROM balance_snapshots;"
```

Run the same query against the database the export came from. They must agree exactly,
including the decimals.

**4. Record it** in the drills table in [ADR 0008](../../docs/adr/0008-local-backups.md), and
drop the scratch database.

```bash
docker compose exec postgres psql -U pfa -d pfa -c "DROP DATABASE pfa_restore_drill;"
```

## Restoring for real

Same command, pointed at the database you mean to fill. It refuses a target that already has
accounts, balances, transactions or card perks unless you pass `--force`, so overwriting a
live database takes saying so twice: once with `--database-url` and once with `--force`.

Restore into a **new Neon branch** first and look at it before pointing anything at it.

## What cannot be rebuilt if this is all lost

Worth knowing, because it sets how much the file is worth.

- **`balance_snapshots` — irreplaceable.** Banks do not serve historical balance-at-a-date,
  and for 401k, HSA, brokerage, property and vehicle values nobody does.
- **`perk_redemptions` — irreplaceable and trivial.** Nothing else records which month you
  used a dining credit.
- Everything else is bank CSVs inside their retention window, or a handful of hand-typed
  rows. Losing it costs an evening, not the history.
