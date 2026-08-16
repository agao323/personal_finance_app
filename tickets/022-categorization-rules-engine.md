# 022 — Categorization rules engine
Status: todo
Wave: 2   Lane: B
Blocked by: 012
Read first: docs/ARCHITECTURE.md#categories--categorization_rules

## Goal
An ordered, user-editable rule set mapping merchant patterns to categories, with manual
overrides always winning.

## Acceptance criteria
- [ ] Rules carry pattern, match type, target category, and priority
- [ ] First match by priority wins
- [ ] `apply_rules()` sets `category_source='rule'` and **never overwrites `category_source='manual'`**
- [ ] Re-running rules over the whole history is safe and idempotent
- [ ] `GET /rules`, `POST /rules`, `PATCH /rules/{id}`, `DELETE /rules/{id}`, `POST /rules/apply`
- [ ] `POST /rules/apply` returns a summary of how many transactions changed
- [ ] A rule can target a `transfer`-kind category, which is how transfers get classified in bulk
- [ ] Tests: unit for priority ordering and manual-override survival; functional asserting a re-run leaves manual categories untouched, and that no match leaves a transaction uncategorised rather than guessing

## Files
- `api/app/models/rule.py`
- `api/app/services/categorize.py`
- `api/app/routers/rules.py`
- `api/tests/test_categorize.py`

## Notes
Without this, every spending chart is subtly wrong and the app stops getting trusted. It is not
a nice-to-have.

The manual-override protection is the whole reason `category_source` exists. Ticket 023 is what
actually writes `'manual'` — until then this protection is untested in practice, so make the
unit test explicit about it.
