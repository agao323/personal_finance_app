import { test as base } from "@playwright/test";

/**
 * Nothing to sign in to.
 *
 * Until ticket 047b this file drove a Chrome CDP virtual authenticator through a real
 * passkey registration, because the app was behind passkeys and an end-to-end run had
 * to actually hold one. Cloudflare Access is the authentication now, and the compose
 * stack has no Access in front of it — `DEV_IDENTITY_EMAIL` names the identity instead,
 * exactly as it does on a developer's laptop. See docs/adr/0007-drop-passkeys.md.
 *
 * Kept as a file rather than deleted so the specs' imports stay put, and because the
 * next thing that needs a shared fixture will want somewhere to go.
 */
export const test = base;

export { expect } from "@playwright/test";
