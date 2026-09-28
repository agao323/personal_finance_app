# 095 — Advisor tables: conversations, turns, messages, tool calls, usage
Status: done
Wave: 10   Lane: L
Touches: **migration** (the first after 0006; serialise) · **contract** (additive re-freeze of `ExportRead`)
Blocked by: 081
Read first: docs/adr/0012-transcripts-live-in-postgres-for-30-days.md, docs/ADVISOR.md#provider-data-handling, docs/ADVISOR.md#numbers

## Goal
The five tables the advisor persists into exist, in one hand-reviewed migration, and are in the
export — so the guard test holds and `make backup` carries them.

## Acceptance criteria
- [x] `models/advisor.py`:
      `advisor_conversations` — uuid id, `user_id` → users `RESTRICT`, `scope`, `title_text`
      (≤ 120, the first question truncated), `created_at`, `last_turn_at`, `expires_at`;
      `advisor_turns` — uuid id, conversation `CASCADE`, `seq`, `status`
      (streaming · complete · cancelled · failed · refused), `grounding` (verified · flagged ·
      none), `model`, `prompt_version`, `error_code`, `started_at`, `finished_at`, and the owner's
      **feedback**: `feedback` (good · flagged · null), `feedback_note_text` (≤ 500),
      `feedback_at`;
      `advisor_messages` — turn `CASCADE`, `seq`, `role`, `content` JSON (content blocks exactly
      as sent or received);
      `advisor_tool_calls` — conversation and turn `SET NULL`, `tool_name`, `tool_call_id`, `args` JSONB, `status`,
      `latency_ms`, `row_count`, `result_bytes`, `withheld_count`, `created_at`;
      `advisor_usage` — turn `SET NULL`, `model`, `request_id`, input, cache-write-5m,
      cache-write-1h, cache-read and output token counts, `stop_reason`, `latency_ms`, `created_at`.
- [x] Column names map one-to-one onto the OpenTelemetry GenAI attributes where one exists
      (`gen_ai.tool.name` → `tool_name`, `gen_ai.tool.call.id` → `tool_call_id`,
      `gen_ai.usage.input_tokens` → `input_tokens`, …); the mapping is written in the module
      docstring.
- [x] **No money column in any of them.** Cost is computed from token counts (ADVISOR.md#numbers);
      a test asserts no `Numeric` column exists in these models.
- [x] Revision 0007 written and reviewed by hand; upgrade and downgrade both exercised by a test.
- [x] Registered in `models/__init__.py` so autogenerate and the schema tests see them.
- [x] All five in `EXPORTED` and `ExportRead`; the export guard passes; a JSON `content` survives
      export and restore unchanged; `make types` run and committed **in its own re-freeze commit**.
- [x] Tests: migration round trip; deleting a conversation removes its turns and messages and
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

## Done — 2026-09-27

- The conversation column is `view`, not `scope`, to match `ConversationCreate.view` and the
  `?view=` every other endpoint takes.
- Small value sets are `CHECK` constraints rather than Postgres enums, so a new turn status is an
  ordinary migration. A test pushes a bad status, grounding and feedback at each one.
- `advisor_usage` gained `provider` (`gen_ai.provider.name`) so a local-model call (120) is never
  priced as a hosted one.
- The export and `restore_local.py` handle UUID keys: the export writes them as strings, restore
  turns them back into `uuid.UUID` for `Uuid` columns.
- The migration was compared against the models with autogenerate on a scratch database: no
  advisor differences. (It reports three unrelated, pre-existing ones — two CHECKs and a functional
  index that autogenerate cannot see — which are not this ticket's.)
- The re-freeze of `ExportRead` is its own commit.
- **Amended in 097, before merge:** `advisor_messages.content` is `JSON`, not `JSONB`. JSONB
  re-sorts object keys, so replayed tool-call arguments came back in a different order — a
  different prompt, and a lost cache. 097's byte-for-byte replay test found it. 0007 had not been
  applied to any lasting database (local dev was at 0006), so the revision was edited in place.
