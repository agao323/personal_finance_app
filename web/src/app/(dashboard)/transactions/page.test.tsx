import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionsScreen } from "./page";
import {
  accounts,
  mockAccounts,
  mockCategories,
  mockTransactionList,
  mockTransactionWrites,
  server,
  transactions,
} from "@/test/msw";

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams.current }));

beforeEach(() => {
  searchParams.current = new URLSearchParams();
  mockAccounts();
  mockCategories();
  mockTransactionList();
  mockTransactionWrites();
});

function table() {
  return screen.getByRole("table", { name: "Transactions" });
}

async function rowCount() {
  // Header row plus one per transaction.
  return within(table()).getAllByRole("row").length - 1;
}

describe("transactions screen", () => {
  it("lists transactions with a count", async () => {
    render(<TransactionsScreen />);

    expect(await screen.findByText("1–3 of 3")).toBeInTheDocument();
    expect(await rowCount()).toBe(3);
  });

  // ── filters ───────────────────────────────────────────────────────────────────

  it("filters by search text", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.type(screen.getByLabelText("Search"), "Unknown");

    await waitFor(async () => expect(await rowCount()).toBe(1));
    expect(within(table()).getByText("Unknown Vendor")).toBeInTheDocument();
  });

  it("filters by account", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");
    // The account options come from /accounts, which loads separately.
    await screen.findByRole("option", { name: "Savings" });

    await userEvent.selectOptions(screen.getByLabelText("Account"), "2");

    await waitFor(async () => expect(await rowCount()).toBe(1));
  });

  it("filters by category", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.selectOptions(screen.getByLabelText("Filter by category"), "11");

    await waitFor(async () => expect(await rowCount()).toBe(2));
  });

  it("filters by date range", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.type(screen.getByLabelText("From"), "2026-08-10");

    await waitFor(async () => expect(await rowCount()).toBe(1));
  });

  it("filters to uncategorised only", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(screen.getByRole("button", { name: "Uncategorised" }));

    await waitFor(async () => expect(await rowCount()).toBe(1));
    expect(within(table()).getByText("Unknown Vendor")).toBeInTheDocument();
  });

  it("opens filtered to uncategorised when the spend view links here", async () => {
    // The loop this closes: spend surfaces uncategorised → this screen fixes it.
    searchParams.current = new URLSearchParams("uncategorised=true");

    render(<TransactionsScreen />);

    await waitFor(async () => expect(await rowCount()).toBe(1));
    expect(screen.getByRole("button", { name: "Uncategorised" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("clears every filter at once", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Uncategorised" }));
    await waitFor(async () => expect(await rowCount()).toBe(1));

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(async () => expect(await rowCount()).toBe(3));
  });

  it("says nothing matched rather than claiming there are no transactions", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.type(screen.getByLabelText("Search"), "zzzzz");

    expect(await screen.findByText("Nothing matches these filters")).toBeInTheDocument();
  });

  // ── inline recategorisation ───────────────────────────────────────────────────

  it("writes a manual category and shows it immediately", async () => {
    const sent: unknown[] = [];
    server.use(
      http.patch("/api/transactions/:id", async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(transactions[0]);
      }),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.selectOptions(
      screen.getByLabelText("Category for Unknown Vendor on Aug 9, 2026"),
      "12",
    );

    await waitFor(() => expect(sent).toEqual([{ category_id: 12 }]));
    // Optimistic: the badge appears without waiting for a refetch.
    expect(await within(table()).findAllByText("manual")).toHaveLength(2);
  });

  it("clears a category and its provenance together", async () => {
    const sent: unknown[] = [];
    server.use(
      http.patch("/api/transactions/:id", async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(transactions[0]);
      }),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    // Row 3 is manually categorised. Clearing it must drop the manual marker too —
    // an uncategorised row still marked manual is one the rules engine will skip
    // for being manual and never categorise again.
    await userEvent.selectOptions(
      screen.getByLabelText("Category for Corner Market on Aug 3, 2026"),
      "",
    );

    await waitFor(() => expect(sent).toEqual([{ category_id: null }]));
    await waitFor(() => expect(within(table()).queryAllByText("manual")).toHaveLength(0));
  });

  it("rolls the row back and says so when the write fails", async () => {
    server.use(
      http.patch("/api/transactions/:id", () =>
        HttpResponse.json({ detail: "Category not found" }, { status: 404 }),
      ),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");
    const picker = screen.getByLabelText("Category for Unknown Vendor on Aug 9, 2026");

    await userEvent.selectOptions(picker, "12");

    expect(await screen.findByRole("alert")).toHaveTextContent("That change was not saved");
    // Put back the way it was: still uncategorised.
    await waitFor(() => expect(picker).toHaveValue(""));
  });

  it("does not revert an unrelated row when one write fails", async () => {
    // Two writes can be in flight at once. A whole-list snapshot would restore the
    // other row's successful change along with the failed one.
    server.use(
      http.patch("/api/transactions/2", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
      http.patch("/api/transactions/:id", () => HttpResponse.json(transactions[0])),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.selectOptions(
      screen.getByLabelText("Category for Corner Market on Aug 3, 2026"),
      "12",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Category for Unknown Vendor on Aug 9, 2026"),
      "11",
    );

    await screen.findByRole("alert");
    // Row 1's successful change survives row 2's failure.
    expect(screen.getByLabelText("Category for Corner Market on Aug 3, 2026")).toHaveValue("12");
  });

  // ── bulk ──────────────────────────────────────────────────────────────────────

  it("categorises a selection in one call", async () => {
    const sent: unknown[] = [];
    server.use(
      http.post("/api/transactions/bulk-categorise", async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json({ updated: 2 });
      }),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select Unknown Vendor on Aug 9, 2026" }),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Category to apply to the selection"),
      "11",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply to 1" }));

    await waitFor(() => expect(sent).toEqual([{ transaction_ids: [2], category_id: 11 }]));
  });

  it("selects every row on the page at once", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(screen.getByRole("checkbox", { name: "Select all on this page" }));

    expect(await screen.findByText("3 selected")).toBeInTheDocument();
  });

  it("rolls back a failed bulk categorise", async () => {
    server.use(
      http.post("/api/transactions/bulk-categorise", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(screen.getByRole("checkbox", { name: "Select all on this page" }));
    await userEvent.selectOptions(
      screen.getByLabelText("Category to apply to the selection"),
      "11",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply to 3" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("put back the way they were");
    expect(screen.getByLabelText("Category for Unknown Vendor on Aug 9, 2026")).toHaveValue("");
  });

  // ── transfers ─────────────────────────────────────────────────────────────────

  it("marks a selected pair as a transfer", async () => {
    const sent: unknown[] = [];
    server.use(
      http.post("/api/transactions/bulk-transfer", async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json({ transfer_group_id: "g1", updated: 2 });
      }),
    );

    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select Unknown Vendor on Aug 9, 2026" }),
    );
    await userEvent.click(
      screen.getAllByRole("checkbox", { name: /^Select Corner Market on Aug 14/ })[0],
    );
    await userEvent.click(screen.getByRole("button", { name: "Mark as transfer pair" }));

    await waitFor(() => expect(sent).toEqual([{ transaction_ids: [2, 1], linked: true }]));
  });

  it("refuses to pair a single row, because a transfer has two sides", async () => {
    render(<TransactionsScreen />);
    await screen.findByText("1–3 of 3");

    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select Unknown Vendor on Aug 9, 2026" }),
    );

    expect(screen.getByRole("button", { name: "Mark as transfer pair" })).toBeDisabled();
  });

  // ── failure ───────────────────────────────────────────────────────────────────

  it("keeps working when the account list cannot be loaded", async () => {
    // The filter row degrades to no account options; the transactions still list.
    server.use(
      http.get("/api/accounts", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    render(<TransactionsScreen />);

    expect(await screen.findByText("1–3 of 3")).toBeInTheDocument();
  });

  it("says transactions are unavailable rather than showing an empty table", async () => {
    server.use(
      http.get("/api/transactions", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    render(<TransactionsScreen />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Transactions unavailable");
  });
});

describe("accounts fixture", () => {
  it("supplies more than one account, so the account filter can discriminate", () => {
    expect(accounts.groups.flatMap((group) => group.accounts).length).toBeGreaterThan(1);
  });
});
