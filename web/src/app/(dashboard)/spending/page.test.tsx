import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import SpendingPage, { DEFAULT_SORT, nextSort, sortBuckets } from "./page";
import type { Bucket } from "@/components/charts/category-breakdown";
import { mockFailure, mockSpend, mockTransactions, parentSpend, server } from "@/test/msw";

beforeEach(() => {
  mockSpend();
  mockTransactions();
});

/** The sortable table, by its caption — the page has more than one table. */
function spendTable() {
  return screen.getByRole("table", { name: /Spending by category/ });
}

function rowNames(): string[] {
  return within(spendTable())
    .getAllByRole("rowheader")
    .map((cell) => cell.textContent ?? "");
}

// ── pure sorting ────────────────────────────────────────────────────────────────

const unsorted: Bucket[] = [
  { category_id: 1, category_name: "Beta", parent_id: null, spend_cents: 100, change_cents: 50 },
  { category_id: 2, category_name: "Alpha", parent_id: null, spend_cents: 300, change_cents: -10 },
  { category_id: 3, category_name: "Gamma", parent_id: null, spend_cents: 200 },
];

describe("sortBuckets", () => {
  it("sorts by spend, largest first, by default", () => {
    expect(sortBuckets(unsorted, DEFAULT_SORT).map((b) => b.category_name)).toEqual([
      "Alpha",
      "Gamma",
      "Beta",
    ]);
  });

  it("sorts by name", () => {
    const sorted = sortBuckets(unsorted, { column: "category", direction: "asc" });

    expect(sorted.map((b) => b.category_name)).toEqual(["Alpha", "Beta", "Gamma"]);
  });

  it("keeps a bucket with no comparison, sorting it as no change", () => {
    // Gamma has no `change_cents`. Dropping it would make a category disappear from
    // a screen because of which column the reader happened to click.
    const sorted = sortBuckets(unsorted, { column: "change", direction: "desc" });

    expect(sorted.map((b) => b.category_name)).toEqual(["Beta", "Gamma", "Alpha"]);
  });

  it("breaks ties by name, so the order does not depend on the API's", () => {
    const tied: Bucket[] = [
      { category_id: 1, category_name: "Zebra", parent_id: null, spend_cents: 500 },
      { category_id: 2, category_name: "Apple", parent_id: null, spend_cents: 500 },
    ];

    expect(sortBuckets(tied, DEFAULT_SORT).map((b) => b.category_name)).toEqual(["Apple", "Zebra"]);
  });

  it("does not mutate the array it was given", () => {
    const original = [...unsorted];
    sortBuckets(unsorted, { column: "category", direction: "asc" });

    expect(unsorted).toEqual(original);
  });
});

describe("nextSort", () => {
  it("flips the direction when the active column is clicked again", () => {
    expect(nextSort({ column: "spend", direction: "desc" }, "spend")).toEqual({
      column: "spend",
      direction: "asc",
    });
  });

  it("starts a money column at its largest end", () => {
    expect(nextSort({ column: "category", direction: "asc" }, "spend")).toEqual({
      column: "spend",
      direction: "desc",
    });
  });

  it("starts a name column at A", () => {
    expect(nextSort({ column: "spend", direction: "desc" }, "category")).toEqual({
      column: "category",
      direction: "asc",
    });
  });
});

// ── the screen ──────────────────────────────────────────────────────────────────

describe("spending", () => {
  it("shows a skeleton before the data arrives, not an empty breakdown", () => {
    render(<SpendingPage />);

    expect(screen.getAllByRole("status", { name: "Loading" }).length).toBeGreaterThan(0);
  });

  it("renders parent categories with the period total", async () => {
    render(<SpendingPage />);

    expect(await screen.findByRole("button", { name: "Housing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Food" })).toBeInTheDocument();
    // $5,000.00 total, and Housing's 50% share of it.
    expect(screen.getByText("$5,000.00")).toBeInTheDocument();
    expect(screen.getAllByText("50.0%").length).toBeGreaterThan(0);
  });

  it("names the comparison window rather than saying 'vs prior'", async () => {
    render(<SpendingPage />);

    // The API compares against the equal-length span before the period, not the
    // previous calendar month. Saying which is the difference between a number the
    // reader can act on and one they have to guess about.
    expect(await screen.findByText(/Compared with the previous \d+ days/)).toBeInTheDocument();
  });

  it("reports the transfers it left out", async () => {
    render(<SpendingPage />);

    expect(await screen.findByText(/2 transfers excluded/)).toBeInTheDocument();
  });

  // ── uncategorised ─────────────────────────────────────────────────────────────

  it("surfaces uncategorised spend with its amount and share", async () => {
    render(<SpendingPage />);

    expect(await screen.findByText("$1,000.00 uncategorised")).toBeInTheDocument();
    expect(screen.getByText(/20\.0% of this period/)).toBeInTheDocument();
  });

  it("offers a direct route to creating a rule", async () => {
    render(<SpendingPage />);

    expect(await screen.findByRole("link", { name: "Create a rule" })).toHaveAttribute(
      "href",
      "/rules",
    );
  });

  it("lists the uncategorised transactions when its bar is drilled into", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: /^Uncategorised:/ }));

    // Only the row with no category — the handler honours `uncategorised=true`.
    const table = await screen.findByRole("table", { name: "Uncategorised transactions" });
    expect(within(table).getByText("Unknown Vendor")).toBeInTheDocument();
    expect(within(table).queryByText("Corner Market")).not.toBeInTheDocument();
  });

  it("links to the transactions screen already filtered to uncategorised", async () => {
    // Looking is not fixing. The callout points at the two places a fix can happen.
    render(<SpendingPage />);

    expect(await screen.findByRole("link", { name: "Categorise them" })).toHaveAttribute(
      "href",
      "/transactions?uncategorised=true",
    );
  });

  it("hides the callout once inside a category, where it would be about something else", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));

    await waitFor(() =>
      expect(screen.queryByText("$1,000.00 uncategorised")).not.toBeInTheDocument(),
    );
  });

  // ── drill-down ────────────────────────────────────────────────────────────────

  it("drills from a parent to its own children only", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));

    expect(await screen.findByRole("button", { name: "Groceries" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restaurants" })).toBeInTheDocument();
    // Housing's children belong to the same response and must not leak in.
    expect(screen.queryByRole("button", { name: "Rent or Mortgage" })).not.toBeInTheDocument();
  });

  it("shows the drilled subtotal, not the whole period", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));

    // Groceries $900 + Restaurants $600 — and it agrees with Food's parent bucket.
    expect(await screen.findByText("$1,500.00")).toBeInTheDocument();
  });

  it("drills from a child to its transactions", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));
    await userEvent.click(await screen.findByRole("button", { name: "Groceries" }));

    const table = await screen.findByRole("table", { name: "Groceries transactions" });
    expect(within(table).getAllByText("Corner Market").length).toBeGreaterThan(0);
    expect(within(table).queryByText("Unknown Vendor")).not.toBeInTheDocument();
  });

  it("walks back up through the breadcrumb", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));
    await userEvent.click(await screen.findByRole("button", { name: "Groceries" }));

    const crumbs = screen.getByRole("navigation", { name: "Category drill-down" });
    await userEvent.click(within(crumbs).getByRole("button", { name: "All categories" }));

    expect(await screen.findByRole("button", { name: "Housing" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Groceries transactions" })).not.toBeInTheDocument();
  });

  it("keeps the breadcrumb on the breakdown, not on the selected row", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));
    await userEvent.click(await screen.findByRole("button", { name: "Groceries" }));
    await screen.findByRole("table", { name: "Groceries transactions" });

    // The trail sits directly above the subtotal, and a number under a label reads
    // as that label's number. Ending the trail in "Groceries" would caption Food's
    // $1,500.00 with the wrong category.
    const crumbs = screen.getByRole("navigation", { name: "Category drill-down" });
    expect(within(crumbs).queryByText("Groceries")).not.toBeInTheDocument();
    expect(within(crumbs).getByText("Food")).toBeInTheDocument();
    expect(screen.getByText("$1,500.00")).toBeInTheDocument();
  });

  it("keeps the selected bar pressed, so the open panel has a visible source", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));
    await userEvent.click(await screen.findByRole("button", { name: "Groceries" }));

    expect(screen.getByRole("button", { name: /^Groceries:/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /^Restaurants:/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  // ── sorting ───────────────────────────────────────────────────────────────────

  it("sorts by spend descending to start with", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });

    expect(rowNames()).toEqual(["Housing", "Food", "Uncategorised"]);
  });

  it("re-sorts by category name when the header is clicked", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });
    await userEvent.click(screen.getByRole("button", { name: /^Category/ }));

    expect(rowNames()).toEqual(["Food", "Housing", "Uncategorised"]);
  });

  it("reverses the active column on a second click", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });
    await userEvent.click(screen.getByRole("button", { name: /^Category/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Category/ }));

    expect(rowNames()).toEqual(["Uncategorised", "Housing", "Food"]);
  });

  it("tells assistive technology which column is sorted", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });

    const headers = within(spendTable()).getAllByRole("columnheader");
    expect(headers[1]).toHaveAttribute("aria-sort", "descending");
    expect(headers[0]).toHaveAttribute("aria-sort", "none");
  });

  it("leaves the chart ranked by spend regardless of the table's sort", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });
    await userEvent.click(screen.getByRole("button", { name: /^Category/ }));

    // The chart is a ranking; re-ordering it by name would make the bars meaningless.
    const bars = within(screen.getByRole("list", { name: /Spending by category/ })).getAllByRole(
      "listitem",
    );
    expect(bars[0]).toHaveTextContent("Housing");
  });

  // ── period ────────────────────────────────────────────────────────────────────

  it("asks the API for the period the reader chose", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/spend", ({ request }) => {
        const params = new URL(request.url).searchParams;
        seen.push(`${params.get("from")}..${params.get("to")}`);
        return HttpResponse.json(parentSpend);
      }),
    );

    render(<SpendingPage />);
    await screen.findByRole("button", { name: "Housing" });
    await userEvent.click(screen.getByRole("button", { name: "This year" }));

    await waitFor(() => expect(seen).toHaveLength(2));
    // Month to date first, then year to date — a January start rather than a monthly one.
    expect(seen[1].slice(5, 10)).toBe("01-01");
  });

  it("returns to the top level when the period changes", async () => {
    render(<SpendingPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Food" }));
    await screen.findByRole("button", { name: "Groceries" });

    await userEvent.click(screen.getByRole("button", { name: "This year" }));

    // The drill was into a category within the old window; keeping it would show a
    // heading for one period over numbers from another.
    expect(await screen.findByRole("button", { name: "Housing" })).toBeInTheDocument();
  });

  it("reveals the date fields for a custom range", async () => {
    render(<SpendingPage />);

    await screen.findByRole("button", { name: "Housing" });
    await userEvent.click(screen.getByRole("button", { name: "Custom" }));

    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(screen.getByLabelText("to")).toBeInTheDocument();
  });

  // ── failure ───────────────────────────────────────────────────────────────────

  it("says the breakdown is unavailable rather than showing an empty one", async () => {
    // A blank breakdown and a breakdown of nothing look identical, and one of them
    // means "you spent nothing this month".
    mockFailure("/api/spend");

    render(<SpendingPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Spending unavailable");
  });

  it("distinguishes a period with no spending from a failure", async () => {
    mockSpend({ buckets: [], total_cents: 0, excluded_transfer_count: 0 });

    render(<SpendingPage />);

    expect(await screen.findByText("No spending in this period")).toBeInTheDocument();
  });
});
