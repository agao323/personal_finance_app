# ADR 0006 — Re-freezing the contract four times during Wave 2

Status: accepted · 2026-08-18 · Backfilled by ticket 039

## Context

Ticket 012 declared the entire v1 API surface — every route, every request and response
model — and generated `web/src/lib/api-types.ts` from it. That freeze is what let three
lanes build in parallel: a frontend ticket could write against the same shapes the
backend was implementing against, and a mismatch was impossible by construction.

`tickets/README.md` says a Wave 2 ticket needing a response-shape change **stops**, gets
the change made in a re-freeze commit, and resumes.

That happened four times.

| Re-freeze | For | What was missing |
|---|---|---|
| `parent_id` on `SpendBucket` | 028 | Nothing told the frontend that Groceries belongs to Food |
| `GET /categories` | 030, 033 | No way to list the taxonomy a picker must offer |
| `POST /transactions/bulk-transfer` | 030 | `TransactionUpdate` carried only `category_id` |
| Preview mapping override, `POST /rules/preview` | 032, 033 | No way to preview a corrected mapping, or a pattern |

## Decision

Make each change additively, in its own commit, with the reason in the commit message —
rather than working around the contract in the frontend.

Every one of the four had a workaround available, and every workaround was worse:

- **028** could have fetched all transactions and grouped by `category.parent_id` in the
  browser. That re-implements the transfer, refund and income rules `services/spend.py`
  applies, and the two would disagree the first time either changed.
- **030's picker** could have derived categories from `/spend?group_by=category`. That
  only returns categories with spending in some window — no income, no transfer — so
  "this was a transfer" becomes inexpressible, which is the correction the screen exists
  to make.
- **030's transfer control** had no field to write at all.
- **033's match preview** could have used `/transactions?search=`. That approximates
  `contains` and nothing else, and `subject_of` falls back to the description when the
  merchant column is empty — a merchant-column `LIKE` misses those entirely. A preview
  that agrees with the engine until the pattern gets subtle is worse than no preview.

## Alternatives considered

**Work around it in the frontend.** Rejected per the above. In every case the workaround
meant computing something in the browser that the server already computes, which is two
implementations of one rule.

**Batch all four into one re-freeze at the end of Wave 2.** Would have meant four tickets
blocked simultaneously, and a single large contract change reviewed at once rather than
four small ones each next to the code that needed it.

**Declare a richer contract in 012.** Tempting in hindsight, and partly right — a
`/categories` endpoint is obvious enough that it should have been there. But the other
three came from working through screens that did not exist yet. Guessing more of them up
front would have declared endpoints nothing ended up needing, which is its own cost.

## Consequences

**Four contract changes in twenty-one tickets is a good hit rate**, not a failed freeze.
The freeze's job was to stop three lanes colliding, and it did — every change was
additive and no lane rebuilt against a changed shape.

**All four were additive.** No field changed type, no field was removed, and no existing
response shape shifted. A frontend built against the old types kept compiling.

**The procedure worked because it was cheap.** Change the Pydantic model, run
`make types`, commit the regenerated file, resume. If it had been expensive there would
have been pressure to take the workaround, and the app would now have two
implementations of the transfer rules.

**In a project without parallel lanes, this ceremony is unnecessary.** The freeze exists
to serialise contract changes across concurrent work. Wave 3 onward has one worker and
changes the contract directly.

## Addendum — 2026-08-20, the first non-additive change

Ticket 047b removed the passkey layer, and with it fourteen routes: the WebAuthn
ceremonies, credential management, invitation redemption, recovery, and logout.
`api-types.ts` lost 806 lines.

Everything above describes re-freezes that **added**, and says so repeatedly, because
every one of them until now did. That was a property of the work rather than a rule, and
it is worth not letting the distinction blur: an additive change cannot break a caller
that has not been updated, and this one can. What made it safe was that Wave 2 had
finished and no lane was building against the removed routes — not the pipeline, which
would have regenerated the file just as happily mid-wave and broken three lanes at once.

The mechanism needed no changes. `make types` regenerated, CI's drift check saw the
removal, and the frozen-signature contract test caught the route inventory before the
suite did. Worth recording that the pipeline handled a deletion without special
treatment, and equally worth recording that it would not have warned anyone if the
deletion had been a mistake.
