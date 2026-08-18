import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TransactionTable, type TransactionRow } from "@/components/transaction-table";
import { transactions } from "@/test/msw";

describe("TransactionTable", () => {
  it("renders a row per transaction with its amount", () => {
    render(<TransactionTable rows={transactions} caption="Groceries transactions" />);

    // Header plus one row each.
    expect(screen.getAllByRole("row")).toHaveLength(transactions.length + 1);
    expect(screen.getByText("−$45.12")).toBeInTheDocument();
  });

  it("shows an inflow without a minus sign", () => {
    // A refund is money back. Rendering it as a negative would make a returned
    // purchase look like a second purchase.
    render(<TransactionTable rows={transactions} caption="Groceries transactions" />);

    expect(screen.getByText("$20.00")).toBeInTheDocument();
  });

  it("names the uncategorised rows rather than leaving the cell blank", () => {
    // An empty cell reads as a rendering bug; "Uncategorised" reads as a fact.
    render(<TransactionTable rows={transactions} caption="All transactions" />);

    expect(screen.getByText("Uncategorised")).toBeInTheDocument();
  });

  it("badges a manual category and nothing else", () => {
    // Manual is the one the rules engine will not overwrite, so it is the one worth
    // explaining. Badging `rule` and `import` too would be noise on every row.
    render(<TransactionTable rows={transactions} caption="All transactions" />);

    expect(screen.getByText("manual")).toBeInTheDocument();
    expect(screen.queryByText("rule")).not.toBeInTheDocument();
  });

  it("marks a transfer, because spend figures exclude it", () => {
    const transfer: TransactionRow[] = [
      {
        ...transactions[0],
        id: 99,
        transfer_group_id: "pair-1",
        category: { id: 31, name: "Credit Card Payment", parent_id: 30, kind: "transfer" },
      },
    ];

    render(<TransactionTable rows={transfer} caption="Transfers" />);

    expect(screen.getByText("transfer")).toBeInTheDocument();
  });

  it("shows the description only when it says something the merchant does not", () => {
    const same: TransactionRow[] = [
      { ...transactions[0], merchant: "Corner Market", description: "Corner Market" },
    ];

    render(<TransactionTable rows={same} caption="Groceries transactions" />);

    const row = screen.getAllByRole("row")[1];
    expect(within(row).getAllByText("Corner Market")).toHaveLength(1);
  });

  it("renders an empty state rather than a headed table with no rows", () => {
    render(
      <TransactionTable rows={[]} caption="Groceries transactions" emptyTitle="Nothing here" />,
    );

    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
