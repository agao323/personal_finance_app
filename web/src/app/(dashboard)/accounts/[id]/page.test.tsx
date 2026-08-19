import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AccountDetailView, stakeRange } from "./page";
import {
  accountDetail,
  mockAccountDetail,
  mockFailure,
  mockTransactions,
  server,
} from "@/test/msw";

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

  it("opens the balance form from the stale-balance prompt", async () => {
    mockAccountDetail({ is_stale: true, balance_as_of: "2026-01-04" });

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText(/carried forward/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Record a newer one" }));

    // The fix is on this page, so the prompt opens it rather than linking away.
    expect(screen.getByLabelText("Balance")).toBeInTheDocument();
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

describe("account management actions", () => {
  it("offers the three write actions, all closed by default", async () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByRole("button", { name: "Record a balance" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: "Change ownership" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close account" })).toBeInTheDocument();
  });

  it("opens one panel at a time", async () => {
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);
    await userEvent.click(await screen.findByRole("button", { name: "Record a balance" }));

    expect(screen.getByLabelText("Balance")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Change ownership" }));

    expect(screen.queryByLabelText("Balance")).not.toBeInTheDocument();
    expect(screen.getByLabelText("New share")).toBeInTheDocument();
  });

  it("says what closing does and does not do", async () => {
    // Closing is not deleting, and a confirmation that only asked "are you sure?"
    // would leave the reader guessing which one they were agreeing to.
    mockAccountDetail();

    render(<AccountDetailView accountId="3" />);
    await userEvent.click(await screen.findByRole("button", { name: "Close account" }));

    expect(screen.getByText(/stops counting toward net worth/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is deleted/)).toBeInTheDocument();
  });

  it("sets closed_at when the close is confirmed", async () => {
    let body: unknown = null;
    mockAccountDetail();
    server.use(
      http.patch("/api/accounts/:id", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(accountDetail);
      }),
    );

    render(<AccountDetailView accountId="3" />);
    await userEvent.click(await screen.findByRole("button", { name: "Close account" }));
    await userEvent.click(
      within(screen.getByText(/Close Rental property\?/).closest("div")!).getByRole("button", {
        name: "Close account",
      }),
    );

    await waitFor(() => expect(body).toEqual({ closed_at: new Date().toISOString().slice(0, 10) }));
  });

  it("offers no write actions on a closed account", async () => {
    mockAccountDetail({ closed_at: "2026-01-01" });

    render(<AccountDetailView accountId="3" />);

    expect(await screen.findByText(/counts toward no total/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record a balance" })).not.toBeInTheDocument();
  });

  it("lets a shared account pick whose share is changing", async () => {
    // There is no /users endpoint, so the owners we can name are the ones already
    // on the account. Ticket 034 turns this into "you".
    mockAccountDetail({
      stakes: [
        { ...accountDetail.stakes[1], percentage_bps: 6_000 },
        {
          ...accountDetail.stakes[1],
          id: 12,
          owner_user_id: 2,
          owner_display_name: "Partner",
          percentage_bps: 4_000,
        },
      ],
    });

    render(<AccountDetailView accountId="3" />);
    await userEvent.click(await screen.findByRole("button", { name: "Change ownership" }));

    expect(screen.getByRole("option", { name: "Partner" })).toBeInTheDocument();
  });
});
