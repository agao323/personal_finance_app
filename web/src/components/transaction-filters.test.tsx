import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  EMPTY_FILTERS,
  TransactionFilters,
  filterQuery,
  isFiltered,
} from "@/components/transaction-filters";
import { categories } from "@/test/msw";

const accounts = [
  { id: 1, name: "Checking" },
  { id: 2, name: "Credit card" },
];

describe("filterQuery", () => {
  it("sends nothing at all when nothing is set", () => {
    // An empty `from=` or `search=` makes the API interpret an empty string.
    expect(filterQuery(EMPTY_FILTERS)).toEqual({});
  });

  it("sends each filter under the API's own parameter name", () => {
    expect(
      filterQuery({
        from: "2026-01-01",
        to: "2026-03-31",
        accountId: 2,
        categoryId: 11,
        uncategorised: null,
        search: "market",
      }),
    ).toEqual({
      from: "2026-01-01",
      to: "2026-03-31",
      account_id: 2,
      category_id: 11,
      search: "market",
    });
  });

  it("drops the uncategorised flag when a category is chosen", () => {
    // A category *is* a categorisation. Sending both is a filter that can only
    // return nothing, which reads as "you have no transactions".
    const query = filterQuery({
      ...EMPTY_FILTERS,
      categoryId: 11,
      uncategorised: true,
    });

    expect(query).toEqual({ category_id: 11 });
  });

  it("sends uncategorised=false for 'categorised only'", () => {
    // Distinct from "any", which sends no flag at all.
    expect(filterQuery({ ...EMPTY_FILTERS, uncategorised: false })).toEqual({
      uncategorised: false,
    });
  });

  it("trims a search term rather than sending the spaces", () => {
    expect(filterQuery({ ...EMPTY_FILTERS, search: "  market  " })).toEqual({ search: "market" });
  });

  it("treats whitespace-only search as no search", () => {
    expect(filterQuery({ ...EMPTY_FILTERS, search: "   " })).toEqual({});
  });
});

describe("isFiltered", () => {
  it("is false for the empty set", () => {
    expect(isFiltered(EMPTY_FILTERS)).toBe(false);
  });

  it("is true once anything narrows the list", () => {
    expect(isFiltered({ ...EMPTY_FILTERS, uncategorised: true })).toBe(true);
  });
});

describe("TransactionFilters", () => {
  it("offers every account plus an any-account option", () => {
    render(
      <TransactionFilters
        filters={EMPTY_FILTERS}
        accounts={accounts}
        categories={categories}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("option", { name: "Any account" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Checking" })).toBeInTheDocument();
  });

  it("offers three categorisation states, not a checkbox", async () => {
    const onChange = vi.fn();
    render(
      <TransactionFilters
        filters={EMPTY_FILTERS}
        accounts={accounts}
        categories={categories}
        onChange={onChange}
      />,
    );

    const group = screen.getByRole("group", { name: "Categorisation" });
    expect(group).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Categorised" }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ uncategorised: false }));
  });

  it("clears the category when a categorisation state is chosen", async () => {
    const onChange = vi.fn();
    render(
      <TransactionFilters
        filters={{ ...EMPTY_FILTERS, categoryId: 11 }}
        accounts={accounts}
        categories={categories}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Uncategorised" }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ uncategorised: true, categoryId: null }),
    );
  });

  it("hides the clear affordance until something is filtered", () => {
    const { rerender } = render(
      <TransactionFilters
        filters={EMPTY_FILTERS}
        accounts={accounts}
        categories={categories}
        onChange={() => {}}
      />,
    );

    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();

    rerender(
      <TransactionFilters
        filters={{ ...EMPTY_FILTERS, search: "market" }}
        accounts={accounts}
        categories={categories}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("stops the date fields from crossing", () => {
    render(
      <TransactionFilters
        filters={{ ...EMPTY_FILTERS, from: "2026-03-01", to: "2026-06-30" }}
        accounts={accounts}
        categories={categories}
        onChange={() => {}}
      />,
    );

    expect(screen.getByLabelText("From")).toHaveAttribute("max", "2026-06-30");
    expect(screen.getByLabelText("To")).toHaveAttribute("min", "2026-03-01");
  });
});
