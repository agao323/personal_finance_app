import { defineConfig, devices } from "@playwright/test";

/**
 * Two smoke tests, run against the compose stack.
 *
 * Deliberately not a second test suite. Vitest covers component behaviour with mocked
 * responses and already numbers in the hundreds; what it cannot tell you is whether
 * the browser, the Next origin, the proxy, the API and Postgres actually join up. That
 * is what these two are for, and adding a third for something a component test already
 * covers just makes CI slower for no new information.
 *
 * No dev server is started here: `make e2e` brings the stack up with the synthetic
 * seed first, because these assert against seeded figures and a half-empty database
 * would fail them for the wrong reason.
 */
export default defineConfig({
  testDir: "./e2e",
  // A CI failure that cannot be reproduced is worse than a slow suite; retry once to
  // tell a flake from a break, and never retry locally where you can just look.
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  // No setup project and no stored session. Ticket 047b removed passkeys, so there is
  // no ceremony to run once and no cookie to carry between tests — the compose stack
  // authenticates by DEV_IDENTITY_EMAIL, the same way a laptop does.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
