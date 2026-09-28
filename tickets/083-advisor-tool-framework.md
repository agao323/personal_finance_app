# 083 — The tool framework: registry, strict schemas, read-only calls, sanitised results
Status: todo
Wave: 9   Lane: —
Touches: none
Blocked by: none
Read first: docs/ADVISOR.md#tools, docs/ADVISOR.md#prompt-injection, docs/ADVISOR.md#transactions-an-exception-to-adr-0005-on-purpose

## Goal
A registry of read-only tools exists. Each tool is a function with a Pydantic input model and a
Pydantic result model; the JSON schema a model sees is generated from the input; arguments are
validated; every call runs in a read-only transaction, is counted against a turn budget, and
returns a sanitised, pre-formatted rendering. Two throwaway test tools exercise it; the real ones
come in 084–093.

## Acceptance criteria
- [ ] `advisor/tools/__init__.py`: a `@tool` decorator registering name, description, input model,
      result model, shape (`aggregate` or `rows`) and whether it is scoped. `schemas()` returns the
      tool definitions **sorted by name**, strict: `additionalProperties: false`, every property in
      `required`, optional parameters nullable.
- [ ] `run(call, ctx)`: validate → check budget → execute → sanitise → render. Invalid arguments
      return an `is_error` result with the reason; an exhausted budget returns `budget_exhausted`.
      Neither raises.
- [ ] Each call runs in its own session, `SET TRANSACTION READ ONLY`, `statement_timeout` 5 s. A
      test tool that attempts an `INSERT` fails with Postgres's read-only error — **in the suite's
      rolled-back fixture and through a real session**, as `tests/test_db.py` does. Record in the
      test which mechanism the fixture needed (a read-only savepoint, or the fallback in
      ADVISOR.md).
- [ ] `ToolContext` carries `today`, the viewer id resolved from the authenticated user, the
      default scope, the turn budget, a session factory and an audit sink (a protocol; in memory
      here, the database in 097). No tool reads the clock.
- [ ] **Schema lint test**: walks every registered tool and fails on any string property without an
      `enum` or a `pattern` plus `maxLength`, any unbounded integer, or any free-text property
      other than `merchant_query` — whose pattern must reject `/` and `:`.
- [ ] `advisor/sanitize.py` implements ADVISOR.md#prompt-injection and is applied to every result
      field ending `_text`. Tested against a corpus of at least 30 strings: zero-width and bidi
      characters, Unicode tag characters, URLs in many shapes, markdown images and links, HTML,
      chat-template tokens, role markers, and every registered tool name.
- [ ] `advisor/render.py` is the one formatter: cents → `$1,234.56` (negatives `-$12.34`), bps →
      `12.3%`, ISO dates, and the envelope `{tool, call, as_of, scope, stale…, data}`, capped at
      8 KB with `truncated`. **Every figure gets a reference id** — `c2.net_worth`,
      `c4.buckets.3.change` — shown beside its display form, and `render.resolve(ref)` returns the
      typed value and canonical form for the grounding check (ADVISOR.md#grounding).
- [ ] Tool conventions, enforced by the lint test where they can be: names namespaced by area
      (`networth_*`, `spend_*`, `cards_*`, `accounts_*`, …); a description of at least two
      sentences saying what the tool answers and which tool to use instead; `detail:
      concise | full` on tools whose full result is large; error messages that say what to do next.
- [ ] `services/analysis/periods.py` resolves the period presets, calendar-aligned, from `today`,
      with span caps; partial periods report the elapsed days so comparisons can be like-for-like.
- [ ] Tests: unit — sanitiser corpus, renderer formats (including half-cent and negative cases),
      schema generation, every period preset on quarter and year boundaries and 29 February;
      functional — read-only enforcement both ways, budget accounting.

## Files
- `api/app/advisor/tools/__init__.py` (new; plus an empty `advisor/__init__.py`)
- `api/app/advisor/sanitize.py` (new)
- `api/app/advisor/render.py` (new)
- `api/app/services/analysis/periods.py` (new; plus an empty `analysis/__init__.py`)
- `api/tests/test_advisor_framework.py`

## Notes
Strict tool schemas and server-side validation are a deliberate pair: `strict: true` makes the
provider emit schema-valid arguments, and Pydantic validates them again here. Eager input streaming
is off because it would switch off the provider's half (ADR 0010).

The sanitiser only ever touches what is sent to a model. Stored data and screens are unchanged —
React already escapes it, and rewriting a merchant name in the database would be a write the
advisor is not allowed to make.
