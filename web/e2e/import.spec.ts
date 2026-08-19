import { expect, test } from "@playwright/test";

/**
 * The CSV import wizard, all four steps, writing to the real database.
 *
 * The one flow where a mistake is expensive and irreversible-feeling, and the one that
 * crosses the most seams: a multipart upload through the Next proxy, a parser, a
 * planner, and an idempotent upsert. Component tests cover each step against MSW; only
 * this covers them meeting.
 */
const CSV = `Date,Description,Amount
2026-05-04,E2E COFFEE HOUSE,-4.25
2026-05-06,E2E BOOK SHOP,-31.90
`;

test.describe("csv import", () => {
  test("walks upload to commit, and a re-import changes nothing", async ({ page }) => {
    await page.goto("/import");

    await page.getByLabel("Import into").selectOption({ index: 1 });
    await page.getByLabel("CSV file").setInputFiles({
      name: "e2e-import.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(CSV),
    });

    // Step 2: the mapping, detected from the header row.
    await expect(page.getByText("Sign convention")).toBeVisible();
    await expect(page.getByLabel("Date")).toHaveValue("Date");

    // Step 3: the rows themselves, not just counts.
    await page.getByRole("button", { name: "Check the result" }).click();
    await expect(page.getByText("E2E COFFEE HOUSE")).toBeVisible();
    await expect(page.getByText("−$4.25")).toBeVisible();

    // Step 4.
    await page.getByRole("button", { name: /^Import/ }).click();
    await expect(page.getByText(/transactions written|Nothing changed/)).toBeVisible();

    // And again: 021's idempotency, proved through the UI rather than asserted.
    await page.getByRole("button", { name: "Import another file" }).click();
    await page.getByLabel("Import into").selectOption({ index: 1 });
    await page.getByLabel("CSV file").setInputFiles({
      name: "e2e-import.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(CSV),
    });
    await page.getByRole("button", { name: "Check the result" }).click();

    await expect(page.getByText(/Nothing here would change/)).toBeVisible();
  });

  test("a bad row is reported against that row, not as a failed file", async ({ page }) => {
    await page.goto("/import");

    await page.getByLabel("Import into").selectOption({ index: 1 });
    await page.getByLabel("CSV file").setInputFiles({
      name: "e2e-broken.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "Date,Description,Amount\n2026-05-04,E2E FINE ROW,-4.25\n31/02/2026,E2E BAD DATE,-9.99\n",
      ),
    });

    await page.getByRole("button", { name: "Check the result" }).click();

    // The good row survives; the bad one names its own problem.
    await expect(page.getByText("E2E FINE ROW")).toBeVisible();
    // Exact: the file-level summary also contains the word "skipped".
    await expect(page.getByText("Skipped", { exact: true })).toBeVisible();
  });
});
