# 114 — Account detail: terms, tax treatment and allocation, where the account is
Status: done
Wave: 12   Lane: W
Touches: none
Blocked by: 112, 113
Read first: docs/ADVISOR.md#data-model-additions

## Goal
The facts Wave 12 adds are entered and read on the account they describe — not on a separate
settings page.

## Acceptance criteria
- [x] On a liability's detail page, a **Terms** panel: APR, minimum payment, credit limit (cards),
      term or maturity, promo rate and end date, and "checked on" with a stale badge past a year.
- [x] On every account, the tax treatment in the account form, with help text for the Roth-401k
      split.
- [x] On investment accounts, an **Allocation** panel: current percentages by class, "unknown" when
      none are set, presets ("target-date 2055 ≈ 90/10", "100% cash"), and the history of changes.
      The form will not save unless the classes total 100.
- [x] Each edit control sits in the panel it edits. Saving a panel updates that panel only.
- [x] Tests (MSW): terms staleness; allocation presets fill the form; a 99.99% total cannot save; a
      save leaves the other panels as they were.

## Files
- `web/src/components/accounts/terms-panel.tsx` (new)
- `web/src/components/accounts/allocation-panel.tsx` (new)
- `web/src/components/forms/account-form.tsx`
- `web/src/app/(dashboard)/accounts/[id]/page.tsx`
- `web/src/components/accounts/allocation-panel.test.tsx`

## Done — 2026-09-28

- A debt's page has a **Terms** panel; an investment account's has an **Allocation** panel and a
  **Tax treatment** line with Change beside it. Cash, property and vehicle accounts show the tax
  line only: their allocation follows from the type, so there is nothing to record.
- Each panel fetches and saves on its own and puts the server's answer in place. A test counts
  the account's reloads and holds them at one across an allocation save and a tax change.
- APRs are typed and shown to three decimals. Terms checked more than a year ago carry the stale
  badge and a line saying to check the latest statement.
- The allocation form fills from two presets, shows its running total, and keeps Save disabled
  until the classes total exactly 100% — 99.99% is tested. History shows each allocation's days,
  ending the day before the next starts.
- The create form offers "Default for this type (…)" and sends a treatment only when one is
  chosen, with the Roth-401(k) hint. Allocation shares now come back in the enum's order (US
  stocks first), matching the history, rather than alphabetically.
- Checked at phone width against synthetic preview data: a brokerage allocation set from the
  target-date preset, and a card's terms saved with a promotion and a stale check date.
