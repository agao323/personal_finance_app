# ADR 0007 — Drop the passkey layer; Cloudflare Access is the authentication

Status: accepted · 2026-08-20 · Ticket 047
Supersedes the passkey half of [ADR 0002](0002-auth.md). The Access half of 0002 stands
unchanged and becomes the whole of it.

## Context

ADR 0002 chose two independent layers: Cloudflare Access at the edge, passkeys in the
application, with the `users` table as the allowlist. The stated reasoning was that
"layer 1 is the security; layer 2 is real, but if it had a flaw, layer 1 would still be
standing."

That was sound when written. It is no longer true, and the thing that changed it was
ours.

### What ticket 044 did to the argument

0002 promised that "a lost passkey is recovered by re-registering from behind Access."
Nothing implemented it, and for a while losing one device meant permanent lockout.
Ticket 044 implemented it: `/auth/recover/*` takes **no session**, verifies the Access
assertion in the API, checks the email against an active `users` row, and registers a
passkey.

That was the right fix for the lockout. It also means **a valid Access assertion is
sufficient to mint a passkey on any device**. The second layer can no longer refuse
anyone the first layer admits. It is not independent; it is downstream.

### What the second layer still bought

Working through the threats, with the `users` allowlist held constant in both designs:

| Threat | Access only | Access + passkeys |
|---|---|---|
| Untargeted internet traffic | Refused at the edge | Refused at the edge; passkeys never consulted |
| The household's Google account is compromised | In | **Also in** — `/recover` issues them a passkey |
| Access policy configured too broadly | Refused by the `users` allowlist | Refused by the same allowlist |
| Request direct to the origin, bypassing Cloudflare | Refused — the API has no public address, the web tier verifies the JWT | Same |
| Physical possession of an unlocked device with a live Access session | **In** | **Refused — needs the platform authenticator** |

One row. The passkey layer defends against physical access to an already-authenticated
device, and nothing else.

### What it cost

About 1,700 lines of source and 1,200 of tests: `services/webauthn.py`,
`services/session.py`, most of `routers/auth.py`, `lib/webauthn.ts`, and five web pages.
Tickets 041, 043, 044, 045, and 046 are all passkey-management work — five of the last
six tickets in the project. Ticket 043 exists **entirely** to answer "how does a second
person obtain a passkey without the owner's session," a question that only exists
because the passkey layer does.

## Decision

**Remove the passkey layer. Cloudflare Access authenticates; the `users` table
authorises.**

- `current_user` resolves the Access-verified email to an active `users` row. Its
  signature is unchanged — the frozen dependency from ticket 012 stays frozen, exactly as
  it did when ticket 034 replaced its implementation with passkeys.
- `services/access.py` is promoted from a recovery detail to the authentication path,
  and keeps verifying the assertion **in the API** rather than trusting a header the web
  tier attached.
- The application holds no credential of its own: no passkeys, no session cookie, no
  `SESSION_SECRET`, and still no passwords.
- Adding a household member becomes a `users` row plus their email on the Access policy.

**This is a reduction in defence in depth and is accepted deliberately**, on these
conditions, which are part of the decision and not aspirations:

1. **The Google account carries a hardware key or passkey**, not SMS or TOTP. It is now
   the entire perimeter and must be the strongest link rather than the weakest.
2. **Access session duration is 24 hours.** This is the mitigation for the row we are
   giving up, and it is a dashboard setting rather than 2,900 lines.
3. **The `users` allowlist stays.** Access says who you are; this app still decides who
   is allowed. Losing that would make an over-broad Access policy a total compromise.
4. **Screen locks on every device**, which is what actually covers the abandoned-laptop
   case in either design.

Further depth, if wanted later, goes **into Access** — device posture, WARP enrolment, a
second identity provider. Cloudflare maintains that; we would have to maintain anything
we build here.

## Consequences

**The blast radius is bounded by what this app can do.** It cannot move money. There is
no transfer, no payment, no external write. A compromise discloses financial history and
can corrupt records; it cannot cause a loss. Corruption is covered by backups once ticket
017 lands — and until it does, that gap is the larger risk of the two, which is worth
saying plainly.

**Demo mode must be handled explicitly, and getting it backwards is a total compromise.**
The demo is public and has no Access in front of it. Today it works by accident: its
`credentials` table is empty, so the bootstrap window in `_bootstrap_user` never closes
and every visitor is served the seeded user. That accident disappears with the bootstrap
window. `demo_mode` must therefore be an explicit branch to a fixed demo identity, and
the rule stays the one ticket 044 established: **absence of a check never reads as a
passing one.** Unconfigured Access outside demo mode refuses.

**Sign-out becomes Cloudflare's.** There is no application session to end, so the only
sign-out is the Access logout — which is precisely the mechanism that failed during the
team rename in ticket 042, because it resolves the organisation out of the cookie it is
trying to clear. The 042 fallback that clears `CF_Authorization` from the origin becomes
more important, not less, and must survive this change.

**The first non-additive contract change.** Every re-freeze so far has been additive.
This removes endpoints. Wave 2 is finished so no lane is building against them, but
`api-types.ts` must be regenerated and the removal is what CI's drift check will see.

**Tables are dropped.** `credentials`, `webauthn_challenges`, and the passkey half of
`invitations`. `ownership_stakes` references `users` and never credentials, so no
historical fact depends on them — but a dropped table is not recoverable by a downgrade
with its rows intact, and the repo's rule that a human reviews every migration applies
with full force here.

**Tickets 045 and 046 are closed as obsolete.** Both describe defects on `/login`, a page
that ceases to exist. They are worth keeping in the tree as a record of what the removed
code was costing.

## Alternatives considered

**Keep passkeys and remove `/recover`.** This is the only variant where the second layer
is genuinely independent again. Rejected because it restores the permanent-lockout
failure that 044 existed to fix, and the household has explicitly ruled out any recovery
that happens outside the website. The trilemma is real: a second factor that can be
re-issued by the first factor is not a second factor, and one that cannot be re-issued is
a lockout waiting for a lost phone.

**Keep the status quo.** Rejected as the worst of both: the maintenance and failure
surface of two layers with the threat model of one. The two bugs found on 2026-08-20 —
a permanently dead button on the sign-in page, and a "your session ended" bar shown to
people who never had a session — were both in code that this decision deletes outright.

**Passwords.** Rejected for the same reason ADR 0002 rejected them, unchanged.

## Verification

To be recorded by ticket 047, in the same table form as ADR 0002. The checks that matter:
an unauthenticated request is still refused at the edge; a request reaching the origin
with no assertion is refused; an email Access authenticates but `users` does not contain
is refused; an inactive user is refused on the next request; and the demo deployment
serves its fixed identity while the real one refuses an unconfigured Access.
