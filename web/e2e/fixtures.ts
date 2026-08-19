import { test as base, type Page } from "@playwright/test";

/**
 * A signed-in page, using a virtual authenticator.
 *
 * The app is behind passkeys, so an end-to-end run has to actually hold one. Chrome's
 * CDP `WebAuthn` domain provides a software authenticator that responds to the real
 * ceremonies, which means these tests exercise tickets 034 and 035 for real rather
 * than around them — the ceremony, the challenge, the signature, and the session
 * cookie are all genuine.
 *
 * It registers rather than signs in because the authenticator is fresh for every run
 * and holds no credential from the last one. `make seed` clears `credentials`, which
 * is what keeps the API's bootstrap window open for it.
 */
export async function signIn(page: Page): Promise<void> {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable");
  await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  await page.goto("/login");
  await page.getByRole("button", { name: "Register a passkey" }).click();
  // The app navigates on success. Waiting for the nav rather than a selector keeps
  // this honest: if the ceremony failed, this fails here rather than three
  // assertions later with a confusing message.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
}

export const test = base;

export { expect } from "@playwright/test";
