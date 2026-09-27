# 0008 — Backups are local exports on the owner's machine

Date: 2026-09-27
Status: accepted
Supersedes: [0004](0004-backups.md)

## Context

[ADR 0004](0004-backups.md) chose nightly encrypted `pg_dump` to Cloudflare R2 from
GitHub Actions, with a dead-man's-switch. The code shipped in August. The manual setup
— an R2 bucket, a scoped token, a healthcheck, seven repository secrets, an encryption
key in a password manager — never happened, so the job ran and failed every night for
five weeks and the schedule was switched off on 26 September.

Reopening it surfaced two things.

**The design concentrated exactly what it claimed to separate.** 0004 said the
encryption key lives "outside Neon, outside R2, outside Fly, outside the repo". True of
the copy in a password manager — but a *working* copy has to sit in GitHub Actions
secrets, next to the R2 credentials and the unpooled database URL. Anyone who
compromises that repository's Actions obtains the live database, the backup store, and
the key that decrypts it. Client-side encryption defends against a leaked bucket and
does nothing against the concentration the architecture itself creates.

**The irreplaceable data is much smaller than the design assumed.** Going table by
table, only `balance_snapshots` is genuinely unreconstructable — banks do not serve
historical balance-at-a-date, and for 401k, HSA, brokerage, property and vehicle values
nobody does. Transactions are recoverable from bank CSVs inside their retention window.
Accounts, institutions, stakes, perks and rules are a handful of hand-typed rows.
`perk_redemptions` is unreconstructable and trivial. Losing everything else means
resuming from today with a shorter chart, not losing the ability to use the app.

The realistic failure modes, in order: losing interest and letting the Neon project
lapse; an owner's own mistake; a Neon incident; compromise. The first three are served
identically by a local copy. The fourth is served *better* by one, because a local copy
is not reachable from the internet at all.

## Decision

**A full JSON export, written to the owner's machine, and nothing offsite that we
operate.**

- **`make backup`** writes `data/backups/pfa-<date>.json` — every table, no exceptions.
  `data/` is gitignored and always has been.
- **Neon's own automatic backups and point-in-time recovery stay as layer one.** They
  are good, they are free, and they require nothing of anybody.
- **The owner's existing machine backup is layer two.** Time Machine or equivalent
  already carries `data/` wherever that machine's backups go.
- **`GET /export`** stays as the escape hatch that works from a browser with no CLI.
- **No encryption on the local file.** FileVault protects the disk, and the file never
  leaves it. A second key to lose was one of the specific objections to 0004, and
  adding one back here would reintroduce the failure it was rejected for.
- **No R2, no GitHub Actions schedule, no healthcheck, no repository secrets.**

## Alternatives considered

**Completing 0004 as written.** Rejected on the concentration argument above, and on
cost: six manual setup steps and a key whose loss is equivalent to losing the database,
in exchange for protecting data that is mostly reconstructible.

**Local export, encrypted.** Rejected. It reintroduces the key-loss failure mode for a
file that never leaves a FileVault-encrypted disk.

**Neon PITR alone.** Tempting, and nearly sufficient. Rejected because it shares fate
with the Neon account: a billing lapse or a mistaken project deletion takes the backups
with the database, and a lapse is the single most likely way this project ends.

**A scheduled local job (launchd).** Not now. A manual `make backup` that is actually
run beats a scheduled one that silently stops, which is the lesson 0004 taught the
expensive way. Worth revisiting once the habit exists.

## Consequences

**Easy.** Nothing to set up, no third-party account, no key to lose, no secret to
rotate. Restoring is reading JSON back into a database, which is a script and not a
runbook of ten steps.

**Hard.** It is manual, so it decays if nobody runs it. The mitigation is honesty
rather than machinery: this is a hobby project for one household, and a command the
owner runs before and after anything significant is proportionate.

**Accepted risk.** A window between the last export and a loss. With a mostly
hand-entered dataset that changes slowly, that window costs a re-entry session, not the
history.

**Worth knowing.** If the machine's backup target is a cloud service, the export
travels there in plain text. `~/Claude` is not a synced location by default, and that
is the assumption here. Moving the repository into a synced folder changes this
decision's basis.

**Foreclosed.** Automatic offsite protection against the machine itself being lost
without its own backup. That is now the owner's backup regime's problem, which is where
it belongs.

## Restore drills

An untested export is not a backup. Record every drill here.

| Date | Export restored | Counts matched | Notes |
|---|---|---|---|
| 2026-09-27 | `pfa-2026-09-27.json`, synthetic seed | yes — all 12 tables | Into a scratch `pfa_restore_drill` database. Sums also compared: balances `45420779.09`, transactions `73418.61`, redemptions `7.50`, all exact. **Found a real bug**: the restore walked `EXPORTED`, the response contract's field order, which puts `ownership_stakes` before `users` — the foreign key refused. Order now comes from `Base.metadata.sorted_tables`. This is the drill earning its keep on its first run. |
| _pending_ | — | — | Repeat against production data before ticket 024 imports anything real. |
