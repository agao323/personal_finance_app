import { expect, test } from "@playwright/test";

/**
 * The dashboard, end to end, against the synthetic seed.
 *
 * Asserts *shapes and relationships* rather than exact figures. The seed is
 * deterministic but its numbers drift with the current date — month-end snapshots are
 * generated relative to today — so pinning "$692,793.29" would make this fail every
 * month for a reason that has nothing to do with the code.
 */
test.describe("dashboard", () => {
  test("renders net worth, runway, and the chart from real data", async ({ page }) => {
    await page.goto("/");

    // A currency figure, not a skeleton and not $0.00.
    const netWorth = page.getByText(/^\$[\d,]+\.\d{2}$/).first();
    await expect(netWorth).toBeVisible();
    await expect(netWorth).not.toHaveText("$0.00");

    await expect(page.getByText("Runway")).toBeVisible();
    await expect(page.getByText(/months$/)).toBeVisible();

    // The chart's data lives in a table so it is reachable without a pointer; that
    // table is also the only honest way to assert the chart has data.
    const chart = page.getByRole("table", { name: /net worth over time/i });
    await expect(chart).toBeAttached();
    expect(await chart.getByRole("row").count()).toBeGreaterThan(3);
  });

  test("the household view is never worth less than mine", async ({ page }) => {
    // The invariant ticket 040 fixed. Worth an E2E because it is a property of the
    // seeded data meeting the ownership service, and neither half can check it alone.
    await page.goto("/");
    const figure = async () =>
      Number((await page.locator("p.text-3xl").first().innerText()).replace(/[$,]/g, ""));

    // Scoped to the tile, not matched across the page. An exact "Net worth" is *not*
    // unique on this dashboard: the tile label and the chart's plot label are both
    // exactly that string, so `getByText(..., { exact: true })` resolves to two elements
    // the moment the chart has data — and before ticket 052 made the series fast, it
    // usually did not, so this passed on a race rather than on being correct.
    const tileLabel = (text: string) =>
      page.locator("p.text-sm", { hasText: new RegExp(`^${text}$`) }).first();

    await page.getByRole("button", { name: "Mine" }).click();
    await expect(tileLabel("Net worth")).toBeVisible();
    const mine = await figure();

    await page.getByRole("button", { name: "Household" }).click();
    await expect(tileLabel("Household net worth")).toBeVisible();
    const household = await figure();

    expect(household).toBeGreaterThanOrEqual(mine);
  });

  test("every screen loads without a client error", async ({ page }) => {
    // The cheapest possible check that no route is dead. A screen that throws on
    // mount renders an error boundary, which no component test would catch because
    // each one mounts its own page in isolation.
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    for (const path of ["/", "/spending", "/accounts", "/transactions", "/import", "/rules"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    }

    expect(errors).toEqual([]);
  });
});
