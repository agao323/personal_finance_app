# 098 — Grounding: figures by reference, policy checks, limitations, and sources
Status: done
Wave: 10   Lane: L
Touches: none
Blocked by: 097
Read first: docs/ADVISOR.md#grounding, docs/ADVISOR.md#policy-checks-on-every-answer, docs/ADVISOR.md#prompt-injection, docs/adr/0011-findings-are-computed-and-figures-are-grounded.md

## Goal
No answer reaches the screen with a figure the tools did not produce, unmarked. The model refers to
figures and the server writes them in; anything it typed itself is checked; the cheap policy checks
run on every answer; an answer that cannot be given says which data is missing; sources are listed
by the system, not the model.

## Acceptance criteria
- [x] **References resolve as the text streams.** `{{c2.net_worth}}` in the model's output is
      replaced with the canonical display form from `render.resolve`, and recorded as a `verified`
      figure with its source call and path. A reference split across stream chunks is buffered
      until complete. An unresolvable reference is left visibly unverified.
- [x] **The backstop.** `advisor/grounding.py` extracts bare money (`$1,234.56`, `$1,235`, `$1.2k`,
      `$1.23M`), percentages and unit counts; ignores dates, years, list ordinals, screen tokens and
      figures from the user's own question; and marks a figure `matched` only in the canonical
      forms of values from this conversation's **typed** tool results — exact, whole dollars
      half-up, one-decimal `k`/`M`, magnitude without sign. Anything else is `unverified`.
- [x] **Policy checks** in `advisor/policy.py`, shared with 102's graders: tickers, fund names and
      issuers (a maintained list; account names exempt); claimed actions; tax limits, brackets or
      rates stated as numbers; scope labels on scoped figures and spend never called a share.
- [x] In the loop: any unverified figure or policy failure gets **one** regeneration, with an
      operator message naming what failed; a second failure ships with the figures marked and a
      visible policy note, and the turn is recorded `grounding: flagged`.
- [x] Answer post-processing strips markdown images and links — **inline and reference-style,
      including the `[1]: https://…` definitions** — autolinks, bare URLs and raw HTML, and keeps
      only screen tokens from the `Screen` enum.
- [x] `note_limitation(capability)` — audit-only, `LimitationKind` enum including `market_data`;
      limitations appear in the `answer` event.
- [x] Citations and lookups assembled from the turn's tool calls: a plain label, arguments summary,
      rows, latency, as-of, scope, stale.
- [x] System prompt addition (097's file): reference figures, never type them.
- [x] Tests: a table of at least 50 answer strings with expected verdicts; `hypothesis` properties —
      every form `render.py` produces for a value is matched, the value ± one cent is not, and every
      reference to an existing path resolves to exactly its canonical form; a reference split
      across chunks; the regeneration path end to end with the scripted model; each policy check
      passing and failing; reference-style image and link stripping; an unknown screen token
      rendered inert.

## Files
- `api/app/advisor/grounding.py` (new)
- `api/app/advisor/policy.py` (new)
- `api/app/advisor/answer.py` (new — post-processing, citations and lookups)
- `api/app/advisor/tools/meta.py` (new — `note_limitation`)
- `api/app/advisor/loop.py`
- `api/tests/test_advisor_grounding.py`

## Notes
Six files, two of them small. If it grows, split the policy checks into their own ticket.

The checker proves where a figure came from, not that the sentence around it is true. Say so in
its docstring; ADR 0011 does.

A small local model may use the reference convention less reliably than a hosted one. That is what
the backstop is for, and the local-model evals report how often each path is taken.

## Done — 2026-09-28

- The pipeline at `end_turn`: `answer.clean` (links, images, HTML, unknown screen tokens) →
  `grounding.check` (references written in, then the backstop) → `policy.check` → at most one
  regeneration. `Grounding` is `verified` when every figure is verified or matched, `flagged`
  when anything unverified or a policy note remains after the retry, `none` with no figures.
- Streamed text resolves references as it arrives; a partial reference is held until it
  completes or cannot. A test streams one string split at every point and one character at a
  time; both equal the final check's text.
- Evidence for earlier turns is rebuilt from their stored tool results (`render.figures_in`),
  so a reference from the last question still resolves.
- Unit counts are matched against every integer and every list length in the conversation's
  results. Years, dates after a month name, ordinals, windows ("the last 3 months") and numbers
  from the question are not checked.
- The retry is a context message stating what failed, as facts. On a model without system
  messages it becomes a user message after the failed answer.
- Tax-figure check: a number in a sentence with both a tax term and a limit term, unless that
  number is a grounded figure. Product check: a maintained issuer and ticker list plus the
  mutual-fund shape (`XXXXX`), exempting the household's own institution and account names.
- Streamed text is not link-stripped as it streams; the `answer` event carries the cleaned text,
  and the web renderer (no `a`, no `img`) and CSP are the other two layers.
- Found in passing, out of scope: `test_net_worth_series` is flaky on the order of
  `stale_account_ids`. Raised as a separate task.
