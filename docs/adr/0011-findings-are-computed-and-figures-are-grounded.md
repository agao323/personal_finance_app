# ADR 0011 — Findings are computed in Python; every figure in an answer is checked

Status: accepted · 2026-09-27 · Ticket 080 — accepted by the owner the day it was proposed

## Context

The constraint is that the model never does money arithmetic: every figure it states comes from a
tool, and sums, deltas, percentages and projections are computed in Python with `Decimal`, through
the existing services. Written as a rule, that is an aspiration. The question is what makes it
true — and what makes a recommendation testable, when the thing producing it is not deterministic.

## Decision

Two mechanisms, one on each side of the model.

**Before it: a findings engine.** Deterministic analyses — spend comparison, trends, recurring
charges, cashflow, net worth attribution, card value, later goals, debt and projections — feed a
findings engine that emits structured findings: kind, severity, evidence with provenance, and an
in-app action. What is worth saying, and how urgent it is, is decided in Python and tested with
hand-computed fixtures. The model explains and prioritises findings for the question asked; it
does not originate them.

**After it: a grounding check.** Every money figure, percentage and unit count in an answer must
match a value from this conversation's tool results, in a canonical form — exact, whole dollars,
or one-decimal `k`/`M`. On a mismatch the answer is regenerated once with the unmatched figures
named; a second mismatch is delivered with those figures marked unverified and the turn flagged.

### Amendment, the same day: figures by reference

A comparison with published practice found *Proof-Carrying Numbers* (2025), which goes one step
further: the model does not type figures at all. It writes a reference (`{{c2.net_worth}}`), the
server writes the value in, and only resolved references count as verified. Adopted as the primary
mechanism; the pattern-matching check above stays as the backstop for any number the model types
itself, which is then marked `matched` or `unverified` rather than verified. The same pass also
runs the cheap policy checks from the evals — tickers, claimed actions, tax figures, scope labels —
on every live answer. Neither changes the decision; both make it harder to get around.

## Alternatives considered

**A prompt instruction alone.** Unverifiable, and it fails silently: a plausible wrong subtraction
reads exactly like a right one.

**A calculator tool, or Anthropic's code-execution tool.** Code execution is a server tool — a
provider-side sandbox that data would enter, which is egress by another name. A calculator is
local and harmless, but the model still chooses the operands, so it proves the arithmetic was done
and not that it was done on the right numbers. Both also move the work *away* from the services
that own the rules (transfers, refunds, ownership, rounding).

**Structured output only.** The model returns finding ids and the UI renders templated text. The
safest option, and a poor answerer of questions nobody templated. It survives anyway, as the
Insights panel — which is exactly this, with no model.

**An LLM judge on every answer.** A second model call per question to check the first. It costs
money on every turn, and it is itself not deterministic. Judging belongs in the evals, where it is
paid once per run.

## Consequences

**Easy.** Recommendations are unit-testable. The Insights panel ships before any model exists. A
model that computes a difference itself is caught and pushed back to the tool that computes it.

**Hard.** Every new kind of derived figure needs a new analysis tool — engineering work that a
free-form model would have waved through. That is the point, and it is also a cost.

**The checker proves provenance, not reasoning.** "Spending rose $412 because of dining" passes if
$412 came from a tool, whether or not dining is why. Semantic correctness is the evals' job, and
the documentation should never claim otherwise.

**Answers read slightly over-precise.** "About $1,200" for $1,234.56 is rejected. A person would
round that way; this system does not let the model decide how.
