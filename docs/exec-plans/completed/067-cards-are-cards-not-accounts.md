# 067 — Cards are cards, not accounts with a subtype
Status: done
Wave: 7   Lane: —
Blocked by: 066

## Goal
Add and manage a card without ever learning that it is an `accounts` row underneath.

## What was wrong

The list said *"A card is an account with the credit card subtype"* and linked to
`/accounts/new`. Two problems, and only one of them is the one that was reported:

- **The copy leaks the schema.** Nobody adding a card needs to know how it is stored.
- **The link is technically fine and practically useless.** `/accounts/new` *can* create a
  credit card — `credit_card` is in `SUBTYPES_BY_KIND` under liability — but only after
  choosing "liability" as the Kind, and that page's own copy says bank and card accounts
  are "usually easier to add by importing a CSV". So it steers you away from the thing it
  can do.

## The data model does not change, and that is deliberate

A credit card's balance is debt. It has to count in net worth, which means it has to be an
account — that is what `AccountKind.LIABILITY` is for. A separate `cards` table would
either duplicate those rows or drop cards out of net worth, and two lists of the same cards
disagree the first time one is renamed or closed.

**What changes is that the interface stops making you learn this.** Cards are created,
renamed and deleted from the cards screen, in card language.

## Acceptance criteria
- [x] Add a card from the cards list: name, issuer, optional annual fee. Creates the
      account and its full ownership stake behind the scenes
- [x] No "account" or "subtype" language anywhere on the cards screen
- [x] The detail's summary is one card-shaped panel containing **the card's name**, its
      figures, and the fee control — not a heading floating above a grid with a link
      underneath it
- [x] That panel's top edge aligns with the list panel beside it
- [x] The synthetic seed gives its credit card an annual fee and several credits across
      different cadences, so a fresh clone opens the cards screen on something real rather
      than an empty state
- [x] Tests: creating a card from the list; the seeded card has perks

## Files
- `api/scripts/seed_synthetic.py`
- `web/src/components/cards/card-list.tsx`, `card-detail.tsx`, `add-card.tsx`

## Done — 2026-09-26

**The reported bug was half right, and the half that was wrong mattered.** `/accounts/new`
*can* create a credit card — `credit_card` sits under liability in `SUBTYPES_BY_KIND` — but
only after choosing the Kind first, while that page's own copy says card accounts are
"usually easier to add by importing a CSV". So the capability was there and everything
around it pointed away from it. Worth separating, because "add the missing subtype" would
have been the wrong fix.

**The storage did not change.** A card's balance is debt and has to count in net worth, so
it stays an account; a separate table would either duplicate those rows or drop cards out of
the figure, and two lists of the same cards disagree the first time one is renamed. What
changed is that nothing on the screen makes you learn that — a test asserts the add form
mentions neither "subtype" nor "liability".

The summary is now one panel carrying the card's name, its figures and the fee control.
Previously the name floated above a bare grid with the fee link stranded below it, reading
as three unrelated things.

The seed grows a second card and credits across four cadences, so a fresh clone opens on
something real. A monthly credit is urgent for most of its life under a fixed threshold and
calm under a per-cadence one, and only a mixture demonstrates that.

Ruff caught an **en dash** in a comment I wrote — the same ambiguous-character family as the
non-breaking space that has bitten this repo twice.
