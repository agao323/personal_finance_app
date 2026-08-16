# Personal Finance App

> **This README is a placeholder.** Ticket 039 replaces it with the real one — screenshots,
> demo link, architecture diagram, setup instructions, and the trade-offs section. Until
> then, this file describes how to *start*.

A personal finance application for one household: net worth with fractional effective-dated
ownership, balance history, spend categorisation, and runway. Next.js + FastAPI + Neon
Postgres, deployed on Fly.io behind Cloudflare Access.

## Where things are

| Path | What |
|---|---|
| `CLAUDE.md` | Loaded into every Claude Code session. Conventions and hard rules. Keep it short. |
| `docs/PRODUCT.md` | What this is and why. The durable source of intent. |
| `docs/ARCHITECTURE.md` | Stack, request path, data model, ownership and snapshot design, hosting. |
| `docs/SECURITY.md` | Threat model, auth, demo isolation, rules for handling real data. |
| `docs/DECISIONS.md` | Project-level decisions, append-only, newest first. |
| `docs/adr/` | Implementation decisions, written as they're made. |
| `tickets/` | The build plan. 39 tickets across 5 waves. |
| `data/` | Real financial exports. Gitignored. Never leaves this directory. |

## Starting the build

```bash
git init && git add -A && git commit -m "000: project plan and conventions"
```

Then, as the first prompt:

> Read CLAUDE.md and tickets/README.md, then implement ticket 001.

That's the whole prompt. Everything else is on disk.

Don't use plan mode for implementation tickets — the plan is already made, and plan mode
would re-derive decisions that are already locked. Reach for it only if a specific ticket
turns out to be gnarlier than its scope suggested.

## Working rhythm

- One ticket per session where possible. Each ends in green tests and a commit.
- If a ticket balloons, split it into `NNNa`/`NNNb` rather than pushing through.
- Adjacent work you notice becomes a new ticket, not scope creep in the current one.
- Session budget is spent on context. Read only the `docs/` files a ticket lists.

## Waves

| Wave | Tickets | Mode | Outcome |
|---|---|---|---|
| 0 — Foundations | 001–008 | serial | Docker, CI, contract pipeline, skeleton live on the internet |
| 1 — Freeze | 009–012 | serial | Whole schema in one migration, ownership + snapshots, contract frozen |
| 2 — Build | 013–033 | 3 parallel lanes | Every feature |
| 3 — Auth & ship | 034–037 | serial | Passkeys, Cloudflare Access, public demo |
| 4 — Close | 038–039 | serial | E2E green, README and ADRs |

Wave 2 runs three lanes in parallel — see `tickets/README.md` for the file-ownership rules
that keep them from colliding.

## Running cost

Roughly **$0–10/month plus a domain**: Neon free tier (two projects), Fly with
`auto_stop_machines`, Cloudflare Zero Trust free tier, Cloudflare R2 free tier for backups,
Sentry and healthchecks.io free tiers, GitHub Actions free on a public repo. Verify current
pricing before committing — these tiers drift.

## Done

The Google Sheet stops being updated. That's the test.
