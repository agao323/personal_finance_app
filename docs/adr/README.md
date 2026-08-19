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

| ADR | Ticket | Subject | Status |
|---|---|---|---|
| `0001-hosting.md` | 008 | Fly + Neon, release-command migrations, private networking | written |
| `0002-auth.md` | 036 | Cloudflare Access + passkeys, and why the origin is private | written |
| `0003-demo-isolation.md` | 037 | Separate Neon projects rather than branches | pending 037 |
| `0004-backups.md` | 017 | Encrypted dumps to R2, and the restore drill | written |
| `0005-request-scoped-transactions.md` | — | The request is the transaction boundary | backfilled by 039 |
| `0006-contract-changes-during-wave-2.md` | — | Re-freezing the contract four times | backfilled by 039 |

0005 and 0006 were backfilled by ticket 039. Both describe decisions that were made
deliberately during implementation but had no ticket calling for an ADR — 0005 because
the bug it documents is the kind that recurs, and 0006 because "we changed the frozen
contract four times" is exactly the sort of thing a later reader would assume was
sloppiness rather than procedure.

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
