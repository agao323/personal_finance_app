import { test as setup } from "@playwright/test";

import { signIn } from "./fixtures";

/**
 * Register one passkey and save the session for the rest of the run.
 *
 * Once, not per test: the API's bootstrap window closes the moment the first
 * credential exists, so a second registration would be refused — correctly. Every
 * test after this reuses the cookie, which is what a real browser does anyway.
 */
const STATE = "e2e/.auth/session.json";

setup("register a passkey", async ({ page, context }) => {
  await signIn(page);
  await context.storageState({ path: STATE });
});

export { STATE };
