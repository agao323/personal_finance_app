import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { AccountDetailView, stakeRange } from "./page";
import { accountDetail, mockAccountDetail, mockFailure, mockTransactions } from "@/test/msw";

beforeEach(() => {
  globalThis.localStorage.clear();
  mockTransactions([]);
});

describe("stakeRange", () => {
  it("reports an open-ended stake as running to now", () => {
    expect(stakeRange(accountDetail.stakes[1])).toBe("Jun 1, 2025 — now");
  });

  it("reports the last day the stake applied, not the day it stopped", () => {
    // Ranges are half-open: `effective_to` of 2025-06-01 means the stake was in
    // force through 31 May. Printing the bound itself would claim a day the stake
    // did not cover, on both sides of the same boundary.
    expect(stakeRange(accountDetail.stakes[0])).toBe("Mar 1, 2024 — May 31, 2025");
  });

  it("steps back across a month boundary correctly", () => {
    expect(
      stakeRange({
        ...accountDetail.stakes[0],
        effective_from: "2026-01-01",
        effective_to: "2026-03-01",
      }),
    ).toBe("Jan 1, 2026 — Feb 28, 2026");
  });
});

describe("account detail", () => {
  it("shows a skeleton before the account arrives", () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    expect(screen.getAllByRole("status", { name: "Loading" }).length).toBeGreaterThan(0);
  });

  it("names the account, its institution, and what kind it is", async () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByRole("heading", { name: "Rental property" })).toBeInTheDocument();
    expect(screen.getByText(/Harbour Trust · Real estate · Illiquid assets/)).toBeInTheDocument();
  });

  it("leads with the adjusted balance and shows the raw one beneath it", async () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText("$225,440.41")).toBeInTheDocument();
    expect(screen.getByText("50% of $450,880.82")).toBeInTheDocument();
  });

  it("lists every stake with the dates it applied, not just the current one", async () => {
    // A bare "50%" is not checkable. The dates are what expose a stake entered
    // against the wrong date, which is otherwise invisible until a chart looks wrong.
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    const table = await screen.findByRole("table", { name: /Ownership stakes/ });
    expect(within(table).getByText("100%")).toBeInTheDocument();
    expect(within(table).getByText("50%")).toBeInTheDocument();
    expect(within(table).getByText("Mar 1, 2024 — May 31, 2025")).toBeInTheDocument();
    expect(within(table).getByText("Jun 1, 2025 — now")).toBeInTheDocument();
  });

  it("says the balance history is raw, because it is not ownership-adjusted", async () => {
    // /accounts/{id}/history takes no view scope. A line drawn at 50% under a
    // heading that did not say so would be quietly wrong.
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText("Raw balance history")).toBeInTheDocument();
  });

  it("puts every history point in a table, not only in the sparkline", async () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    const table = await screen.findByRole("table", { name: /Raw balance history/ });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByText("$440,000.00")).toBeInTheDocument();
  });

  it("prompts to record a newer balance when one is being carried forward", async () => {
    mockAccountDetail({ is_stale: true, balance_as_of: "2026-01-04" });

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText(/carried forward/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record a newer one" })).toHaveAttribute(
      "href",
      "/import",
    );
  });

  it("says a closed account has no balance instead of showing zero", async () => {
    mockAccountDetail({
      closed_at: "2026-01-01",
      balance_cents: null,
      adjusted_balance_cents: null,
      balance_as_of: null,
    });

    render(<AccountDetailView accountId="3" />);

    expect(
      await screen.findByText(/No balance on record — this account is closed/),
    ).toBeInTheDocument();
  });

  it("warns when an account has no stake at all", async () => {
    // Every account is supposed to get an explicit 100% row at creation. One with
    // none contributes nothing to net worth, silently.
    mockAccountDetail({ stakes: [] });

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText("No ownership stake recorded")).toBeInTheDocument();
  });

  it("keeps the page when the history fails, because the balance is the fact", async () => {
    mockAccountDetail();
    mockFailure("/api/accounts/:id/history");

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText("$225,440.41")).toBeInTheDocument();
    expect(screen.queryByText("Raw balance history")).not.toBeInTheDocument();
  });

  it("says the account is unavailable when it cannot be loaded", async () => {
    mockFailure("/api/accounts/:id", 404);

    render(<AccountDetailView accountId="999" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Account unavailable");
  });

  it("offers a way back to the list from the error state", async () => {
    mockFailure("/api/accounts/:id", 404);

    render(<AccountDetailView accountId="999" />);

    await screen.findByRole("alert");
    expect(screen.getByRole("link", { name: "← All accounts" })).toHaveAttribute(
      "href",
      "/accounts",
    );
  });
});
