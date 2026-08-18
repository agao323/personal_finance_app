# 017 — Backups, tested restore, and data export
Status: in-progress
Wave: 2   Lane: A
Blocked by: 008
Read first: docs/SECURITY.md#backups

## Goal
Automated encrypted backups with failure alerting, a restore actually performed once, and a
full data export endpoint. **This ticket gates real data entering production.**

## Acceptance criteria
- [ ] Nightly `pg_dump` to Cloudflare R2, encrypted, 30-day retention
- [ ] Encryption key stored outside Neon and outside the repo
- [ ] **A dead-man's-switch** (healthchecks.io or equivalent) that alerts when the job fails to check in
- [ ] **A restore performed into a scratch database and verified** — row counts and a spot-checked aggregate. Use a **Neon branch of the real project** as the scratch target; that is what branches are for and it costs nothing.
- [x] Restore procedure documented step by step, runnable by someone who didn't write it
- [x] `GET /export` returning the full dataset as JSON
- [x] Tests: unit for the encryption round-trip and the R2 upload path (mocked); functional for `/export` against the synthetic seed

## Files
- `api/scripts/backup.py`
- `api/scripts/restore.md`
- `api/app/routers/export.py`
- `docs/adr/0004-backups.md`
- `api/tests/test_backup.py`

## Notes
The tested restore is the acceptance criterion, not the backup job. Moving out of Google Sheets
into a self-run database is a durability downgrade until a restore has actually been proven.

**No real data enters production until this is done** — ticket 024 runs against a local
database until then.

This ticket is only blocked by 008, so it can be pulled into whichever lane has capacity. It
lives in Lane A because Lane A is the shallowest.

The alerting is not optional garnish: a backup job that silently stops working is worse than no
backup, because it is trusted.

## Status — 2026-08-18: code done, four manual steps remain

Everything authorable is written, tested, and merged. `GET /export` is live.

**These need accounts and a payment method, so they are yours to run.** Until they are
done there are no backups, which is why this ticket gates ticket 024.

1. **Create an R2 bucket** — Cloudflare dashboard → R2 → Create bucket, name it
   `pfa-backups`. Then Manage API tokens → create one scoped to that bucket with
   Object Read & Write. Note the account ID for the endpoint URL.

2. **Generate an encryption key and store it in your password manager**, not anywhere
   else:
   ```bash
   cd api && uv run python scripts/backup.py --print-key
   ```
   Losing this loses every backup. That is the deliberate trade in ADR 0004.

3. **Create a healthchecks.io check** (free tier). Period: 1 day, grace: 6 hours —
   GitHub delays scheduled runs under load, so a tight grace period alerts on
   lateness rather than failure. Copy its ping URL.

4. **Add the GitHub Actions secrets** (Settings → Secrets and variables → Actions):
   `BACKUP_DATABASE_URL` (the **unpooled** Neon string — `pg_dump` opens one long
   connection and does not want PgBouncer), `R2_BUCKET`, `R2_ENDPOINT_URL`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `BACKUP_ENCRYPTION_KEY`,
   `BACKUP_HEALTHCHECK_URL`.

Then trigger it once by hand — Actions → Nightly backup → Run workflow — and confirm
an object lands in the bucket.

**Then run the restore drill** in `api/scripts/restore.md` and record it in the table
in ADR 0004. That drill, not the backup job, is this ticket's acceptance criterion.
