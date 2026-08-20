# 047b — Remove the passkey layer
Status: todo
Wave: 5   Lane: —
Blocked by: 047a
Read first: docs/adr/0007-drop-passkeys.md

## Goal
Delete WebAuthn, the application session cookie, and every screen that existed to manage
them. After 047a nothing authenticates through them; this removes the code, the tables,
and the secret.

## Acceptance criteria

**Delete**
- [ ] `api/app/services/webauthn.py`, `api/app/services/session.py`
- [ ] From `api/app/routers/auth.py`: `/auth/register/*`, `/auth/login/*`,
      `/auth/logout`, `/auth/credentials*`, `/auth/recover/*`. `GET /auth/session`
      **stays** — the account menu needs to say whose numbers these are
- [ ] `current_identity` and `CurrentIdentity` from `deps.py`, and `_bootstrap_user` with
      them. The bootstrap window is the thing 043 and 044 were both working around
- [ ] `web/src/lib/webauthn.ts`, `web/src/app/login/`, `web/src/app/recover/`,
      `web/src/app/(dashboard)/settings/passkeys/`, `web/src/components/session-expiry.tsx`
- [ ] `SESSION_SECRET` from config, both fly configs, compose, CI, and the ticket-034
      startup guard that refuses to boot on its default value

**Change**
- [ ] `web/src/proxy.ts` keeps the Access check and **loses the session-cookie check and
      the `/login` redirect**. There is no longer a sign-in page to redirect to
- [ ] The 042 behaviour — clearing `CF_Authorization` on a failed assertion — **must
      survive**, and its tests with it. It becomes the only in-browser recovery from a
      stuck Access session, so it matters more after this ticket than before
- [ ] `PUBLIC_PREFIXES` drops `/login` and `/recover`. `/invitation` goes only if 043's
      redemption flow goes with it
- [ ] The account menu shows the display name from `GET /auth/session` and a single
      **Sign out of Cloudflare Access**. Note in the code that this is Cloudflare's
      logout, which is the mechanism that failed during the rename in 042
- [ ] Decide `invitations` explicitly. Its entire purpose was attaching a passkey to a
      new member's account; adding a member is now a `users` row plus the Access policy.
      If the table goes, say so in the ticket's Done note rather than leaving it dead

**Migration**
- [ ] Drops `credentials` and `webauthn_challenges`. Hand-written and **human-reviewed**,
      per the repo rule — never `--autogenerate` and commit blind
- [ ] Confirm no foreign key outside the passkey tables references them.
      `ownership_stakes.owner_user_id` points at `users` and must be untouched: a stake is
      a historical fact and 010 made it `ON DELETE RESTRICT` for that reason

**Contract**
- [ ] Re-freeze. **This is the first non-additive change** — every previous one added.
      Wave 2 is finished so no lane is building against the removed routes, but
      `make types` must run and `api-types.ts` be committed, or CI's drift check fails
- [ ] Record it in `docs/adr/0006-contract-changes-during-wave-2.md`, which currently
      documents four additive re-freezes and should not imply that was the only kind

**Docs and tickets**
- [ ] `docs/SECURITY.md#auth` and `docs/ARCHITECTURE.md` describe what the code does.
      Both currently describe passkeys as load-bearing
- [ ] `docs/runbooks/going-live.md` — the passkey registration steps go; adding a member
      becomes the `users` row plus the Access policy
- [ ] Fill in ADR 0007's **Verification** table, in ADR 0002's format. "It should be
      private" is not the same as having checked
- [ ] Close **045** and **046** as obsolete — both describe defects on `/login`. Keep the
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
