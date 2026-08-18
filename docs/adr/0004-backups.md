# 0004 — Backups: encrypted nightly dumps to R2, with a dead-man's-switch

Date: 2026-08-18
Status: accepted

## Context

[SECURITY.md](../SECURITY.md#backups) makes the case plainly: moving a financial
picture out of Google Sheets, which Google backs up, into a self-operated database is
a **durability downgrade until backups are proven**. Neon's own automatic backups and
point-in-time recovery are real and are the first layer, but they share a fate with
the Neon account itself — a billing lapse, a mistaken project deletion, or a
compromised login takes the backups with the database.

The threat model ranks *database and backups at rest* second, above session hijack and
above traffic interception. A backup file is a complete financial picture in a single
object, and unlike the live database it tends to sit somewhere less carefully guarded.

## Decision

**Nightly `pg_dump` from GitHub Actions, encrypted client-side, to Cloudflare R2, with
30-day retention and a dead-man's-switch.**

- **Custom-format dump**, not plain SQL: `pg_restore` can then work selectively and in
  parallel, and it compresses on the way out.
- **Encrypted before upload** with Fernet, using a key held in a password manager —
  outside Neon, outside R2, outside Fly, outside the repo.
- **GitHub Actions on a schedule**, not a Fly cron machine. The job needs `pg_dump`,
  `boto3`, and the encryption key, none of which the runtime image should carry, and a
  scheduled workflow is one file where a cron machine is several.
- **A healthcheck ping on every run**, with an explicit failure ping so an alert fires
  immediately rather than at the next missed window.
- **`GET /export`** returns the whole dataset as JSON, independent of all of the above.

## Alternatives considered

**Relying on Neon's PITR alone.** It is genuinely good and it is the first layer. It
lost as a *sole* strategy on the shared-fate argument: it lives in the same account as
the thing it protects, so the failures that take out the database can take it out too.
Two independent layers for $0 is the whole reason Neon was chosen over a self-operated
Postgres in [ADR 0001](0001-hosting.md).

**Server-side encryption at R2.** Simpler — one checkbox — but the object store holds
the keys, so it protects against a stolen disk and not against a compromised R2 token
or a misconfigured bucket. Client-side encryption means the bucket contents are
useless to anyone who obtains them, which is the actual threat.

**No encryption, private bucket only.** Rejected. A public-by-accident bucket is a
well-populated genre of incident, and the blast radius here is every balance and every
transaction.

**A Fly cron machine.** Keeps everything on one platform, but means a machine that
exists to run once a day, plus `pg_dump` and `boto3` in the runtime image for a job the
API never performs.

**Alerting on failure only.** The failure this design fears most is not a job that
errors — it is a job that stops running. A schedule silently disabled, a repository
made inactive, a workflow renamed. Only a dead-man's-switch catches that, because only
the *absence* of a signal is evidence of it.

## Consequences

**Easy.** Restores are a documented sequence into a Neon branch. Backup contents are
useless to anyone who obtains the bucket. Cost is zero — R2's free tier is 10 GB with
no egress fees, and these dumps are tens of megabytes.

**Hard.** **If the encryption key is lost, every backup is unrecoverable.** That is the
deliberate trade: a key the platform could recover for you is a key an attacker can
obtain the same way. The key belongs in a password manager, and losing it should be
treated as the same severity as losing the database.

**Foreclosed.** Point-in-time recovery to an arbitrary second, which nightly dumps
cannot provide. Neon's own PITR covers that window — the two layers are complementary
rather than redundant.

**Obligation.** The restore drill is not optional and not one-time. `api/scripts/restore.md`
is the runbook; the table below is the evidence.

## Restore drills

An untested backup is not a backup. Record every drill here.

| Date | Backup restored | Counts matched | Notes |
|---|---|---|---|
| _pending_ | — | — | First drill must run before any real data enters production — see ticket 024. |
