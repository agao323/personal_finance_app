import { expect, test } from "@playwright/test";

/**
 * Capture the README's screenshots.
 *
 * A spec rather than a script so it reuses the signed-in session and the seeded
 * database the rest of the run already sets up. Skipped unless asked for: it writes
 * files into the repo, which a test has no business doing on every run.
 */
const CAPTURE = process.env.CAPTURE_SCREENSHOTS === "1";

test.describe("screenshots", () => {
  test.skip(!CAPTURE, "set CAPTURE_SCREENSHOTS=1");

  test("capture", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });

    for (const [path, name] of [
      ["/", "dashboard"],
      ["/spending", "spending"],
      ["/accounts", "accounts"],
      ["/transactions", "transactions"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      // Let the charts finish their fetch before capturing a skeleton.
      await page.waitForTimeout(1200);
      await page.screenshot({ path: `../docs/images/${name}.png` });
    }
  });
});
