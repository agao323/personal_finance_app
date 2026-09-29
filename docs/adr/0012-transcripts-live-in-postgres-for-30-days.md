# ADR 0012 — Advisor transcripts live in Postgres for 30 days

Status: proposed · 2026-09-27 · Plan 122 — the retention choice was made by the owner on this date

## Context

A conversation holds the household's finances in prose: the questions asked, and tool results with
figures in them. SECURITY.md asks where transcripts live, if anywhere, and that has to be decided
rather than fallen into.

Two things pull toward keeping them. Follow-up questions need the earlier turns — "and last year?"
means nothing on its own. And the grounding check accepts a figure only if a tool returned it in
this conversation, which is only a guarantee if the server holds those tool results itself.

## Decision

**Transcripts are stored server-side in Postgres, and deleted 30 days after a conversation's last
turn.**

- Tables: `advisor_conversations`, `advisor_turns`, `advisor_messages` (content blocks exactly as
  sent and received, so history replays byte for byte — which prompt caching needs, and which the
  API requires for thinking blocks).
- Each person sees their own conversations. Deleting one removes it immediately.
- The tool-call log (`advisor_tool_calls`) is kept **90 days** and survives deletion: an audit log
  its subject can erase is not one. It holds validated arguments, never results.
- Token usage (`advisor_usage`) is kept 13 months, for cost history. It holds counts, not content.
- Purged lazily at the start of every advisor request, and by `make advisor-purge`. **No
  scheduler.**
- All five tables are in `/export`, so the export guard holds and `make backup` carries them.

## Alternatives considered

**Not stored — the browser holds the conversation.** The least at rest. But the server would then
receive earlier tool results *from the client* on every turn, and could not trust them, so
grounding would shrink to the current turn. A reload would lose the chat. The audit log alone
would still be kept.

**Stored until deleted.** More to look back on, and financial prose accumulating indefinitely in a
database and in every backup. The value of a three-month-old conversation is low; its figures are
stale by then anyway.

**A shorter TTL — a day, a week.** Plausible. Thirty days covers "what did it say last month"
around a monthly review, and matches the provider's own retention, so neither side holds a
transcript much longer than the other.

**Excluding transcripts from `/export`.** Would need an exception mechanism in the guard that
exists to stop tables falling out of the export. Not worth weakening for data that expires anyway.

## Consequences

**Easy.** Follow-ups work, grounding spans the conversation, and history replays exactly.

**Hard, and to be said out loud in the UI.** A conversation deleted today still exists in any
`make backup` file written before today, and in the provider's copy for up to 30 days. The delete
confirmation says so.

**The purge has to actually run.** Lazy purging means an unused advisor keeps expired transcripts
until someone opens it. With no scheduler that is the accepted trade, and `make advisor-purge` is
the manual lever. Worth revisiting if ADR 0008's launchd idea is ever adopted for backups.
