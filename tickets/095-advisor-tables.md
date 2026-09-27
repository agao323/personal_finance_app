# 095 — Advisor tables: conversations, turns, messages, tool calls, usage
Status: todo
Wave: 10   Lane: L
Touches: **migration** (the first after 0006; serialise) · **contract** (additive re-freeze of `ExportRead`)
Blocked by: 081
Read first: docs/adr/0012-transcripts-live-in-postgres-for-30-days.md, docs/ADVISOR.md#provider-data-handling, docs/ADVISOR.md#numbers

## Goal
The five tables the advisor persists into exist, in one hand-reviewed migration, and are in the
export — so the guard test holds and `make backup` carries them.

## Acceptance criteria
- [ ] `models/advisor.py`:
      `advisor_conversations` — uuid id, `user_id` → users `RESTRICT`, `scope`, `title_text`
      (≤ 120, the first question truncated), `created_at`, `last_turn_at`, `expires_at`;
      `advisor_turns` — uuid id, conversation `CASCADE`, `seq`, `status`
      (streaming · complete · cancelled · failed · refused), `grounding` (verified · flagged ·
      none), `model`, `prompt_version`, `error_code`, `started_at`, `finished_at`;
      `advisor_messages` — turn `CASCADE`, `seq`, `role`, `content` JSONB (content blocks exactly
      as sent or received);
      `advisor_tool_calls` — conversation and turn `SET NULL`, `tool`, `args` JSONB, `status`,
      `latency_ms`, `row_count`, `result_bytes`, `withheld_count`, `created_at`;
      `advisor_usage` — turn `SET NULL`, `model`, `request_id`, input, cache-write-5m,
      cache-write-1h, cache-read and output token counts, `stop_reason`, `latency_ms`, `created_at`.
- [ ] **No money column in any of them.** Cost is computed from token counts (ADVISOR.md#numbers);
      a test asserts no `Numeric` column exists in these models.
- [ ] Revision 0007 written and reviewed by hand; upgrade and downgrade both exercised by a test.
- [ ] Registered in `models/__init__.py` so autogenerate and the schema tests see them.
- [ ] All five in `EXPORTED` and `ExportRead`; the export guard passes; a JSONB `content` survives
      export and restore unchanged; `make types` run and committed **in its own re-freeze commit**.
- [ ] Tests: migration round trip; deleting a conversation removes its turns and messages and
      leaves its tool-call rows with `conversation_id` null; export includes a synthetic
      conversation.

## Files
- `api/app/models/advisor.py` (new), `api/app/models/__init__.py`
- `api/alembic/versions/0007_advisor.py` (new)
- `api/app/schemas/export.py`, `api/app/routers/export.py`
- `api/tests/test_advisor_models.py`

## Notes
Tool-call rows outlive their conversation on purpose: an audit trail its subject can erase is not
one. They hold validated arguments and counts, never results.

Only one ticket may have a migration in flight. This one goes first; 108, 109, 112 and 113 follow
it in that order.
