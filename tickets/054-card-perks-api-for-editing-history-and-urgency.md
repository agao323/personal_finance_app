# 054 — Card perks API: editing, deleting, history, urgency
Status: todo
Wave: 7   Lane: —
Blocked by: 053
Read first: tickets/050-card-perks-api.md

## Goal
Every endpoint the rebuilt page needs. After this, tickets 055–059 are frontend-only and
can run in parallel.

## Acceptance criteria
- [ ] `DELETE /perks/{perk_id}` — **refused with 409 when the perk has any redemption.**
      Deleting one that was genuinely used would erase history; retiring
      (`is_active = false`, already in 050) is the answer there. Delete exists for the
      perk you added by mistake, and the response says which case you hit
- [ ] `GET /perks/{perk_id}/history` — every redemption, newest first, with the period it
      belongs to, the amount (face value when `NULL`), and the note. Covers **first
      redemption to most recent**, with an optional `from`/`to` window
- [ ] `GET /cards/history` — the same across every card, for the whole-wallet view.
      Optional window; **no default cut-off**, because "show me everything" is the
      request that was actually made
- [ ] `POST /perks/{perk_id}/redemptions` accepts an optional `amount_cents`, and still
      accepts `on` for backfilling a past period. Marking twice stays idempotent; a
      second mark with a different amount **updates** it rather than erroring
- [ ] `GET /perks/upcoming` gains `is_urgent` per perk from `services/perks.is_urgent`,
      and keeps `within_days` as a caller-supplied horizon. Default raised to **90** so
      an annual credit is visible without asking
- [ ] `GET /cards` reports, per card: perk count, available value this period, and — when
      `annual_fee` is set — fee and value realised in the current fee year
- [ ] `PATCH /accounts/{id}` already renames a card; assert it in a test here so the
      rebuild does not discover it is missing
- [ ] Update the endpoint table in `docs/ARCHITECTURE.md` — the contract test parses it
- [ ] Re-freeze the contract: `make types`, commit `api-types.ts`
- [ ] Tests: the 409 on deleting a used perk and the 204 on an unused one; history
      ordering and windowing; a partial amount round-tripping as cents; re-marking with a
      new amount; urgency true/false at each cadence boundary; totals in `GET /cards`

## Files
- `api/app/routers/cards.py`
- `api/app/schemas/card_perk.py`
- `api/tests/test_cards.py`
- `docs/ARCHITECTURE.md`

## Notes

**History comes from stored `period_start`**, never recomputed from a cadence that may
have been edited since — 049 made that choice and this ticket depends on it.

Every date is still a parameter. Nothing in this area reads the clock.
