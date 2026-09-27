# 075 — SimpleFIN connector: transactions, and credits marked from them
Status: planning
Wave: 8   Lane: —
Blocked by: none — 017 is done; the production restore drill it left pending gates real data (see below)
Read first: docs/ARCHITECTURE.md#account-sources, docs/SECURITY.md

## Goal
Credit card transactions arrive nightly from SimpleFIN instead of by CSV, and a credit is
marked used because a matching transaction exists rather than because you remembered to tap
it. The same transactions fill the transactions page, replacing manual import for the
accounts that are connected.

**This ticket is a plan, not an implementation.** It is one ticket because it is one
decision; it ships as the phases below, each cut as its own ticket when this is picked up.
Nothing here is built yet.

## Why SimpleFIN

[ARCHITECTURE.md#account-sources](../../ARCHITECTURE.md#account-sources) already decided
the shape: every account carries a `source`, connectors are strictly additive behind a
`SourceAdapter` interface, and `DataSource.SIMPLEFIN` has been in the enum since the first
migration. This is the anticipated path, not a reversal — but it is the first real
connector, so the interface that was specified in v1 and never built gets built here.

Verified against the protocol and the Bridge on 27 September 2026:

| | |
|---|---|
| Protocol | SimpleFIN 2.0.0-draft (spec dated 19 March 2026) |
| Cost | $1.50/month or $15/year, up to 25 institutions and 25 apps |
| Access | Read-only. The app never sees bank credentials |
| American Express | **Supported.** Search returns American Express, American Express (Canada), American Express @Work – Subaccounts, and Bread Rewards |
| Auth | Setup token → base64-decode → `POST` → Access URL with Basic Auth credentials embedded |
| Data | `GET {access}/accounts?version=2` returns accounts with balances and transactions |
| Rate limit | **≤24 requests per day.** Sustained excess disables the access token |
| Window | **90 days maximum** per request. History depth varies by institution |

## The constraints that drive the design

**The rate limit is the architecture.** Twenty-four requests a day, and exceeding it
sustained gets the token disabled — not throttled. So: one scheduled fetch, never a fetch on
page load, never a "refresh" button that calls upstream. Anything the screen shows comes from
our own tables.

**Ninety days per request** means the historical backfill is a paged job, roughly nine
requests for two years, which is most of a day's quota. It runs once, deliberately, not as
part of connecting.

**The Bridge asks for a 5-day overlap** between windows so late-posting transactions are not
missed. Overlap means re-fetching rows we already have, which is free: `transactions` already
carries `external_id` with a partial unique index per account, and ingestion is upsert by
contract. This is the property that makes a sloppy window safe.

**`posted` is not when you spent it.** The protocol carries `posted` (required) and
`transacted_at` (optional). A purchase on 31 January posting on 2 February belongs to
January's monthly credit, and matching on `posted` would put it in February's — the same
class of bug as the fee year. Match on `transacted_at` when the institution provides it, fall
back to `posted`, and record which was used.

**Amounts are numeric strings**, which is the right shape: parse straight to `Decimal`. Never
through `float`. Rule 5 holds.

## Phases

### Phase 1 — The adapter and the connection
Build `SourceAdapter` for real, with `fetch_accounts()`, `fetch_balances()`,
`fetch_transactions()`, and move the existing manual and CSV paths behind it so the interface
has two implementations before it has one consumer.

A `connections` table holds one claimed Access URL per SimpleFIN connection, plus
`last_synced_at` and the last error. Claiming is one-time: the setup token is spent on first
POST, and a 403 there means the token may be compromised and must be said so, not swallowed.

**The Access URL is a credential**, with Basic Auth embedded in it. It is stored encrypted at
rest, keyed from a Fly secret, never logged, never in an error message, never in a response
body. This wants a short ADR of its own alongside `docs/SECURITY.md` — the next free
number, 0009 at the time of writing (0008 is local backups).

Linking a SimpleFIN account to one of ours is a manual mapping step — their `id` and `name`
against our accounts — reusing the `import_mappings` idea rather than guessing by name.

### Phase 2 — Nightly sync
A scheduled job, at a random minute rather than on the hour, as the Bridge asks. Fetches the
trailing window with 5 days of overlap, upserts on `(account_id, external_id)`, appends a
balance snapshot per rule 7, and records what it did.

Backfill is a separate one-shot command walking ≤90-day windows backwards until the
institution stops returning rows, rate-limited to stay inside the daily quota. It reports how
far back it actually got, because that varies per institution and "we have your whole
history" must not be assumed.

`errlist` is surfaced to the screen, sanitised. A connection needing re-authentication is the
normal failure here and has to be visible, not silent.

### Phase 3 — Matching transactions to credits
A `perk_match_rules` table: perk, merchant pattern, amount bounds, direction. Same shape as
`categorization_rules`, which is already ordered-by-priority with first match winning, so the
matching engine has a precedent to copy rather than invent.

Two different signals, and they are not equally good:
- **The statement credit** — a positive amount from the issuer. Proof the credit was actually
  granted. Often generically described.
- **The qualifying purchase** — a negative amount at a matching merchant. Arrives sooner, but
  proves only that you spent, not that the credit posted.

Start with the qualifying purchase, because it is what a merchant pattern can actually
identify, and treat it as evidence rather than proof.

### Phase 4 — Proposals, not silent marks
The matcher writes **proposals**, and a person confirms them. `perk_redemptions` gains a
source and a link to the transaction that suggested it, so a matched mark is distinguishable
from one you made and can say what it was matched from.

Two rules that are not negotiable:
- **The matcher never overwrites a human mark.** A mark you made by hand is the better
  record, always.
- **The matcher never un-marks.** The absence of a transaction is not evidence you did not
  use a credit — pending transactions are excluded by default, coverage is per-institution,
  and history is shallow at the edges. Auto-unmarking would delete real records on missing
  data. Unmarking stays a person's decision. *(This narrows "assign credits as used or
  unused" deliberately; see Open decisions.)*

## Open decisions
1. **Proposals or direct marks?** Proposed above: propose, confirm in one tap from the
   existing period grid. A wrong auto-mark costs a $200 credit you then never use. Once the
   rules have been right for a few months, promoting high-confidence rules to auto-mark is a
   small change.
2. **Does connecting a card replace its manual balance entry?** It should, but rule 7 says
   every balance write appends a snapshot, and a nightly connector writing 365 snapshots a
   year for an account you also edit by hand needs a precedence rule.
3. **What happens to CSV import for a connected account?** Leaving both live invites the same
   transaction arriving twice with different ids from different sources. The `external_id`
   index does not protect across sources.
4. **Cards only, or everything?** The ask is credit cards. Connecting checking and savings too
   is nearly free once the adapter exists, but each connected institution is real data landing
   in a database whose restore has not yet been proven against real data. See the gate below.

## Gated on a proven restore, and this is not a formality
[SECURITY.md](../../SECURITY.md) argues that moving a financial picture out of Google Sheets
into a self-run database is a durability downgrade until backups are proven. Nightly
connectors are the point at which this database becomes the only copy of something — a
transaction history no CSV on disk reproduces. Ticket 024 is already held for this reason and
this is the same rule.

*Updated 2026-09-27 (ticket 080).* This section was written when 017 meant the R2 design,
and listed an R2 bucket, seven repository secrets and a schedule. 017 replaced all of that
with local exports ([ADR 0008](../../adr/0008-local-backups.md)) and is done; its first
restore drill passed against synthetic data. What still stands between this plan and real
data is the drill against a **production** export — ADR 0008's pending row — the same gate
that holds 024. Tracked as TD-003 in the
[tech-debt tracker](../tech-debt-tracker.md).

## Testing
Fixtures are recorded SimpleFIN responses, hand-edited to synthetic values — rule 1, and the
demo token's data is not a substitute because it will change under us. No test talks to the
network. The matcher gets a table of transaction/perk pairs with hand-computed expected
matches, including the 31 January purchase that posts in February, which is the case the
whole `transacted_at` decision exists for.

## Cost of not doing it
Marking credits by hand takes seconds a month and the period grid (069) made it cheap. The
real prize is the transactions page: it is the only part of this app still fed by a manual
export, and it is the reason the Google Sheet has not been switched off.
