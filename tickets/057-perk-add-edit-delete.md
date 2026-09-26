# 057 — Add, edit, and remove a credit
Status: todo
Wave: 7   Lane: W3
Blocked by: 054
Read first: tickets/054-card-perks-api-for-editing-history-and-urgency.md

## Goal
The form for a credit, working in all three directions. Editing and deleting are the two
things the current page cannot do at all.

## Acceptance criteria
- [ ] One form component for add and edit — name, value, cadence, anchor date, description
- [ ] **Edit** an existing perk via `PATCH /perks/{id}`, prefilled
- [ ] **Delete** via `DELETE /perks/{id}`, confirmed first. When the API answers 409
      because the perk has history, say so and offer **retire** instead — the API's own
      message, not a local paraphrase that could drift
- [ ] Retire and un-retire (`is_active`), with retired perks visibly separate rather than
      hidden. A retired perk you cannot see is one you will add again by mistake
- [ ] The anchor-date field keeps its explanation. "First period began" is guessable only
      with the sentence under it, and a wrong anchor silently shifts every period for that
      perk — this is still the field most likely to be filled in wrong
- [ ] Changing a cadence or anchor warns that existing history keeps its recorded periods.
      That is correct — `period_start` is a stored fact — but it is surprising unless said
- [ ] Tests: add; edit prefills and saves; delete confirms; the 409 path offers retire;
      validation refuses a zero value and a missing anchor

## Files
- `web/src/components/cards/perk-form.tsx`
- `web/src/components/cards/perk-form.test.tsx`

## Notes

Owns its component file only, so it runs alongside 055, 056, 058, 059.

Reuse `MoneyInput` from `components/forms/fields` — it reports integer cents and keeps the
raw text, so a half-typed "12." is not destroyed.
