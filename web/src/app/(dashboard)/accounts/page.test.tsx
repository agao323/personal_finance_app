import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import AccountsPage, { partition } from "./page";
import { accounts, mockAccounts, mockFailure } from "@/test/msw";

beforeEach(() => {
  globalThis.localStorage.clear();
});

/** One account's row, by the link that wraps it. */
async function row(name: string | RegExp) {
  return await screen.findByRole("link", { name });
}

describe("partition", () => {
  it("keeps the groups in spend-own-owe order", () => {
    expect(partition(accounts).open.map((g) => g.kind)).toEqual([
      "liquid_asset",
      "illiquid_asset",
      "liability",
    ]);
  });

  it("pulls closed accounts out of their kind group", () => {
    const { open, closed } = partition(accounts);

    expect(closed.map((a) => a.name)).toEqual(["Old car"]);
    const illiquid = open.find((g) => g.kind === "illiquid_asset")!;
    expect(illiquid.accounts.map((a) => a.name)).toEqual(["Rental property"]);
  });

  it("uses the API's subtotals rather than re-adding the rows", () => {
    // The server rounds once per account. A browser-side sum of already-rounded
    // values is not guaranteed to match, and net worth must have one source.
    const illiquid = partition(accounts).open.find((g) => g.kind === "illiquid_asset")!;

    expect(illiquid.adjustedCents).toBe(22_544_041);
  });

  it("drops a group with no open accounts rather than showing an empty card", () => {
    const onlyClosed = {
      ...accounts,
      groups: accounts.groups.map((g) => (g.kind === "liability" ? { ...g, accounts: [] } : g)),
    };

    expect(partition(onlyClosed).open.map((g) => g.kind)).toEqual([
      "liquid_asset",
      "illiquid_asset",
    ]);
  });

  it("returns nothing for no data, rather than throwing", () => {
    expect(partition(null)).toEqual({ open: [], closed: [] });
  });
});

describe("accounts list", () => {
  it("groups accounts by kind with a subtotal each", async () => {
    mockAccounts();

    render(<AccountsPage />);

    expect(await screen.findByText("Liquid assets")).toBeInTheDocument();
    expect(screen.getByText("Illiquid assets")).toBeInTheDocument();
    expect(screen.getByText("Liabilities")).toBeInTheDocument();
    // Liquid subtotal, unadjusted because both stakes are 100%.
    expect(screen.getByText("$44,517.40")).toBeInTheDocument();
  });

  it("shows no grand total, because assets plus liabilities is not a quantity", async () => {
    // The API's `total_cents` adds a mortgage to a brokerage. Net worth is computed
    // in one place and shown on the dashboard.
    mockAccounts();

    render(<AccountsPage />);

    await screen.findByText("Liquid assets");
    expect(screen.queryByText("$477,954.99")).not.toBeInTheDocument();
  });

  it("shows adjusted and raw side by side where a stake splits them", async () => {
    mockAccounts();

    render(<AccountsPage />);

    // The rental is half owned: $225,440.41 of $450,880.82. Scoped to the row —
    // it is the only open illiquid account, so the group subtotal is the same
    // number, which is realistic and makes an unscoped query ambiguous.
    const rental = await row(/Rental property/);
    expect(within(rental).getByText("$225,440.41")).toBeInTheDocument();
    expect(within(rental).getByText("50% of $450,880.82")).toBeInTheDocument();
  });

  it("does not repeat the balance when the stake is 100%", async () => {
    mockAccounts();

    render(<AccountsPage />);

    const checking = await row(/Checking/);
    expect(within(checking).getByText("$1,377.17")).toBeInTheDocument();
    expect(within(checking).queryByText(/100% of/)).not.toBeInTheDocument();
  });

  it("names the scope of an adjusted subtotal", async () => {
    mockAccounts();

    render(<AccountsPage />);

    expect(await screen.findByText(/your share of \$450,880\.82/)).toBeInTheDocument();
  });

  it("flags a stale balance with how old it is", async () => {
    mockAccounts();

    render(<AccountsPage />);

    expect(await screen.findByText(/Updated \d+ months ago/)).toBeInTheDocument();
  });

  it("separates closed accounts and says they count toward nothing", async () => {
    mockAccounts();

    render(<AccountsPage />);

    const closed = (await screen.findByText("Closed")).closest("section")!;
    expect(within(closed).getByText("Old car")).toBeInTheDocument();
    expect(within(closed).getByText(/count toward no total/)).toBeInTheDocument();
  });

  it("says a closed account has no balance rather than showing zero", async () => {
    // "$0.00" is a claim about money. "No balance" is a claim about data.
    mockAccounts();

    render(<AccountsPage />);

    const closed = (await screen.findByText("Closed")).closest("section")!;
    expect(within(closed).getByText("No balance")).toBeInTheDocument();
  });

  it("links each account to its detail page", async () => {
    mockAccounts();

    render(<AccountsPage />);

    expect(await screen.findByRole("link", { name: /Rental property/ })).toHaveAttribute(
      "href",
      "/accounts/3",
    );
  });

  it("routes an empty account list to the import flow", async () => {
    mockAccounts({ groups: [], total_cents: 0, adjusted_total_cents: 0 });

    render(<AccountsPage />);

    expect(await screen.findByText("No accounts yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import transactions" })).toHaveAttribute(
      "href",
      "/import",
    );
  });

  it("refetches for the household scope", async () => {
    mockAccounts();

    render(<AccountsPage />);

    await screen.findByText("Liquid assets");
    await userEvent.click(screen.getByRole("button", { name: "Household" }));

    // Both the illiquid group and the liabilities group carry a split subtotal.
    expect((await screen.findAllByText(/household share of/)).length).toBe(2);
  });

  it("says accounts are unavailable rather than rendering an empty list", async () => {
    mockFailure("/api/accounts");

    render(<AccountsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Accounts unavailable");
  });
});
