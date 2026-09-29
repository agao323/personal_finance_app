# 060 — Seeding a card's perks from a catalogue
Status: todo — needs a decision, see below
Wave: 7   Lane: —
Blocked by: 057
Read first: docs/exec-plans/completed/053-card-perks-schema-for-partial-use-and-fees.md

## The question
Can we learn that an Amex Platinum carries a $200 airline credit, a $200 hotel credit and
a $15 monthly Uber credit — without typing them in?

## What the investigation found

**The catalogue is public. Usage is not.** This is the finding that matters, and it is the
opposite of the earlier conclusion about Amex data: *whether you have used your credit*
needs your account and is a non-starter (no API, MFA, bot detection — see the
statement-credit approach instead). *What credits the card carries* is marketing copy on a
public product page. No login, no scraping of an authenticated session.

Structured third-party sources exist:

| Source | Coverage | Licence / cost | Carries cadence? |
|---|---|---|---|
| [OpenCard-DB](https://github.com/thedavidweng/opencard-db) | 189 cards, 3 countries | MIT code, **CC BY 4.0 data** | Not evident — schema centres on fees and points categories |
| [CardAPI](https://cardapi.dev/) | "hundreds", 39 issuers, daily refresh | free tier 100 calls/day, then $29/mo | Claims "structured statement credits"; schema not published, unverifiable without a key |
| Scraping issuer product pages | anything | public content, ToS applies | No — prose |

## Why this is harder than it looks, and it is not the access

Three problems, none of which a catalogue solves:

1. **`anchor_on` is per-cardholder and exists in no catalogue.** The single most important
   field on a perk — the date its first period began — depends on when *you* opened the
   card. A catalogue cannot know it. Every seeded perk would still need that field filled
   in by hand, which is the field the UI already warns is easiest to get wrong.
2. **Benefit terms vary by cohort.** The same product name carries different credits
   depending on when it was opened and which refresh you are on; Amex reworked the
   Platinum's benefits substantially in 2025–26. A catalogue describes the current
   offering, not your contract.
3. **Calendar year versus cardmember year is frequently unstated**, and getting it wrong
   is exactly the failure this app is built to avoid — a credit reported available when it
   is spent.

So a catalogue is worth **typing saved, not correctness gained**. It gets most rows roughly
right and the ones it gets wrong are silently wrong.

## Proposed shape, if we do it
- [ ] "Suggest credits for this card" — proposes rows you accept, edit or discard
- [ ] **Never auto-creates.** Same rule as statement-credit detection: it proposes, you
      confirm. A wrong perk is worse than an absent one, because you would trust it
- [ ] Every suggested row lands with `anchor_on` **empty and required** before saving
- [ ] The source and the date it was fetched are recorded on the perk, so a stale
      suggestion is identifiable later
- [ ] One issuer's catalogue first, behind an interface, so a second source is additive

## The decision needed

**Is this worth it for a two-card household?** Typing four credits takes five minutes and
is done once per card. This ticket is a network dependency, a mapping layer, a licence
obligation (CC BY attribution) or a subscription, and a class of silently-wrong data — to
save that five minutes.

My read: **not yet.** Revisit if the household reaches a point where cards turn over often
enough that seeding pays for itself, or if CardAPI's schema turns out to carry real cadence
data, which would change the fidelity argument rather than the convenience one. Written down
so the option is documented rather than rediscovered.
