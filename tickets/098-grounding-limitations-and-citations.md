# 098 — Grounding: every figure checked; limitations recorded; sources cited
Status: todo
Wave: 10   Lane: L
Touches: none
Blocked by: 097
Read first: docs/ADVISOR.md#grounding, docs/ADVISOR.md#prompt-injection, docs/adr/0011-findings-are-computed-and-figures-are-grounded.md

## Goal
No answer reaches the screen with a figure the tools did not produce, unmarked. An answer that
cannot be given says which data is missing, in a form the evals can grade. Sources are listed by
the system, not by the model.

## Acceptance criteria
- [ ] `advisor/grounding.py` extracts money (`$1,234.56`, `$1,235`, `$1.2k`, `$1.23M`), percentages
      and unit counts; ignores dates, years, list ordinals, screen tokens and figures from the
      user's own question; and accepts only the canonical forms of values from this
      conversation's **typed** tool results — exact, whole dollars half-up, one-decimal `k`/`M`,
      magnitude without sign, percentages at the given precision or whole.
- [ ] In the loop: on a mismatch, one regeneration with an operator message naming the unmatched
      figures; on a second, the answer ships with those spans `unverified` and the turn
      `grounding: flagged`.
- [ ] Answer post-processing strips markdown images and links, autolinks, bare URLs and raw HTML,
      and keeps only screen tokens from the `Screen` enum.
- [ ] `note_limitation(capability)` — audit-only, `LimitationKind` enum; limitations appear in the
      `answer` event.
- [ ] Citations assembled from the turn's tool calls: a plain label per call, as-of, scope, stale.
- [ ] Tests: a table of at least 50 answer strings with expected verdicts; `hypothesis` properties
      — every form `render.py` produces for a value is accepted, and that value ± one cent is
      rejected; the regeneration path end to end with the scripted model; image, link and HTML
      stripping; an unknown screen token rendered inert.

## Files
- `api/app/advisor/grounding.py` (new)
- `api/app/advisor/answer.py` (new — post-processing and citations)
- `api/app/advisor/tools/meta.py` (new — `note_limitation`)
- `api/app/advisor/loop.py`
- `api/tests/test_advisor_grounding.py`

## Notes
The checker proves where a figure came from, not that the sentence around it is true. Say so in
its docstring; ADR 0011 does.

"About $1,200" for $1,234.56 is rejected, deliberately. If that reads stiff in practice, widen the
canonical forms here — in one place, with a test — rather than loosening the match.
