# 047b — Remove the passkey layer
Status: done
Wave: 5   Lane: —
Blocked by: 047a
Read first: docs/adr/0007-drop-passkeys.md

## Goal
Delete WebAuthn, the application session cookie, and every screen that existed to manage
them. After 047a nothing authenticates through them; this removes the code, the tables,
and the secret.

## Acceptance criteria

**Delete**
- [x] `api/app/services/webauthn.py`, `api/app/services/session.py`
- [x] From `api/app/routers/auth.py`: `/auth/register/*`, `/auth/login/*`,
      `/auth/logout`, `/auth/credentials*`, `/auth/recover/*`. `GET /auth/session`
      **stays** — the account menu needs to say whose numbers these are
- [x] `current_identity` and `CurrentIdentity` from `deps.py`, and `_bootstrap_user` with
      them. The bootstrap window is the thing 043 and 044 were both working around
- [x] `web/src/lib/webauthn.ts`, `web/src/app/login/`, `web/src/app/recover/`,
      `web/src/app/(dashboard)/settings/passkeys/`, `web/src/components/session-expiry.tsx`
- [x] `SESSION_SECRET` from config, both fly configs, compose, CI, and the ticket-034
      startup guard that refuses to boot on its default value

**Change**
- [x] `web/src/proxy.ts` keeps the Access check and **loses the session-cookie check and
      the `/login` redirect**. There is no longer a sign-in page to redirect to
- [x] The 042 behaviour — clearing `CF_Authorization` on a failed assertion — **must
      survive**, and its tests with it. It becomes the only in-browser recovery from a
      stuck Access session, so it matters more after this ticket than before
- [x] `PUBLIC_PREFIXES` drops `/login` and `/recover`. `/invitation` goes only if 043's
      redemption flow goes with it
- [x] The account menu shows the display name from `GET /auth/session` and a single
      **Sign out of Cloudflare Access**. Note in the code that this is Cloudflare's
      logout, which is the mechanism that failed during the rename in 042
- [x] Decide `invitations` explicitly. Its entire purpose was attaching a passkey to a
      new member's account; adding a member is now a `users` row plus the Access policy.
      If the table goes, say so in the ticket's Done note rather than leaving it dead

**Migration**
- [x] Drops `credentials` and `webauthn_challenges`. Hand-written and **human-reviewed**,
      per the repo rule — never `--autogenerate` and commit blind
- [x] Confirm no foreign key outside the passkey tables references them.
      `ownership_stakes.owner_user_id` points at `users` and must be untouched: a stake is
      a historical fact and 010 made it `ON DELETE RESTRICT` for that reason

**Contract**
- [x] Re-freeze. **This is the first non-additive change** — every previous one added.
      Wave 2 is finished so no lane is building against the removed routes, but
      `make types` must run and `api-types.ts` be committed, or CI's drift check fails
- [x] Record it in `docs/adr/0006-contract-changes-during-wave-2.md`, which currently
      documents four additive re-freezes and should not imply that was the only kind

**Docs and tickets**
- [x] `docs/SECURITY.md#auth` and `docs/ARCHITECTURE.md` describe what the code does.
      Both currently describe passkeys as load-bearing
- [x] `docs/runbooks/going-live.md` — the passkey registration steps go; adding a member
      becomes the `users` row plus the Access policy
- [ ] Fill in ADR 0007's **Verification** table, in ADR 0002's format. "It should be
      private" is not the same as having checked
- [x] Close **045** and **046** as obsolete — both describe defects on `/login`. Keep the
      files; they are the record of what this code was costing
- [ ] Set Access session duration to **24 hours** and confirm the Google account carries a
      hardware key or passkey. Both are conditions of ADR 0007, not follow-ups

## Files
- `api/app/routers/auth.py`, `api/app/deps.py`
- `api/alembic/versions/0004_drop_passkeys.py`
- `web/src/proxy.ts`, `web/src/components/account-menu.tsx`
- plus the deletions listed above

## Notes

**Do this in the order written.** The deletions are safe only because 047a already moved
authentication off them; running any part of this before 047a is verified would leave the
app briefly with no working sign-in at all.

**Dropping a table is not reversible by a downgrade.** The rows do not come back. Take a
dump first — and note that ticket 017 is still open, so there is no automated backup
standing behind this. That ordering is worth reconsidering before running the migration
against production.

**Resist re-adding a second factor here.** ADR 0007 accepted a reduction in defence in
depth on stated conditions, and further depth belongs in Access — device posture, WARP,
a second identity provider — where Cloudflare maintains it. Anything rebuilt in this
codebase re-acquires the maintenance surface this ticket removes.

## Done — 2026-08-20

**Two things were deleted that this ticket did not anticipate, and both mattered.**

The end-to-end suite drove a Chrome CDP virtual authenticator through a real passkey
registration, with a `setup` project and a stored session so the ceremony ran exactly
once. All of it went. What replaced it is nothing: the compose stack has no Access in
front, so `DEV_IDENTITY_EMAIL` names the identity and the specs just run.

And the compose stack had no identity configured at all — the API service passed only
`DATABASE_URL`. Left alone, `make dev` and `make e2e` would have come up with every
request refused. Found by reading the compose file rather than by a failing test, which
is the wrong way round; the suite runs on the host and never noticed.

**`invitations` was dropped**, as the ticket asked to decide explicitly. It existed to
break a loop — a new member could not register a passkey without a session and could not
get a session without a passkey — and Access authenticates them now, so there is no loop.
Adding someone is a `users` row plus the Access policy.

**The migration's downgrade had to recreate every index, not just every table.** 0001,
0002 and 0003 each drop their own on the way down, so tables restored without them make
*those* downgrades fail rather than this one. The `upgrade → downgrade → upgrade` test
caught it; nothing else would have, since the upgrade path is clean either way.

It also normalises `users.email` to lowercase and adds a unique index on `lower(email)`.
047a matches the Access-verified email case-insensitively, which made two rows differing
only in case consequential — previously possible and harmless, now a question of which
member you are signed in as.

**The contract lost 806 lines** — the first non-additive re-freeze this project has had.
Recorded as an addendum to ADR 0006, which described four additive ones and said so
enough times that a reader would reasonably infer a rule.

**What was kept deliberately:** `GET /auth/session`, because the account menu still has
to say whose numbers these are; and 042's clearing of `CF_Authorization` on a failed
assertion, which is now the *only* in-browser way out of a stuck Access session and is
noted as such in `proxy.ts`, `routers/auth.py`, and `SECURITY.md`.

Guards 19, API 447, web 404.

**Not done here, and not mine to do:** the Access session duration and the Google
hardware key are dashboard settings, and ADR 0007's verification table needs the deployed
app. Both are unticked above.
