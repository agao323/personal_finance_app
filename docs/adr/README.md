# Architecture Decision Records

One file per decision made **during implementation**. Project-level decisions made before
coding live in `../DECISIONS.md`.

Write the ADR while making the decision, not afterward. Ten minutes each. Retrospective
ADRs are reconstructions and read like it.

## When to write one

- You chose between two viable options and the loser had real merit.
- You did something non-obvious that a reader would otherwise flag as a mistake.
- You accepted a known cost or limitation on purpose.

Not for: routine implementation, library versions, anything with an obvious answer.

## Why these matter here

This project is built across many sessions with no shared memory between them, and it'll be
maintained for years by someone who has forgotten the details — future me. An ADR is how a
decision survives that. Without one, a later session re-litigates a settled question, or
worse, silently reverses it because the reasoning was never written down.

## Planned

Tickets that call for an ADR by name:

| ADR | Ticket | Subject |
|---|---|---|
| `0001-hosting.md` | 008 | Fly + Neon, release-command migrations, private networking |
| `0002-auth.md` | 036 | Cloudflare Access + passkeys, and why the origin is private |
| `0003-demo-isolation.md` | 037 | Separate Neon projects rather than branches |

Others get written as they come up. Ticket 039 backfills anything missed.

## Format

```markdown
# NNNN — Title

Date: YYYY-MM-DD
Status: accepted | superseded by NNNN

## Context
The situation that forced a decision. Constraints in play.

## Decision
What was chosen, stated plainly.

## Alternatives considered
What else was viable, and the actual reason it lost. "It was worse" is not a reason.

## Consequences
What this makes easy. What it makes hard. What it forecloses. Be honest about the costs —
an ADR listing only benefits is marketing.
```

Numbering is sequential from `0001`. Never renumber; supersede instead.
