import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  CategoryBreakdown,
  isUncategorised,
  shareOfTotal,
  type Bucket,
} from "@/components/charts/category-breakdown";

const buckets: Bucket[] = [
  {
    category_id: 6,
    category_name: "Housing",
    parent_id: null,
    spend_cents: 250_000,
    prior_period_cents: 240_000,
    change_cents: 10_000,
  },
  {
    category_id: null,
    category_name: "Uncategorised",
    parent_id: null,
    spend_cents: 100_000,
    prior_period_cents: 60_000,
    change_cents: 40_000,
  },
];

describe("shareOfTotal", () => {
  it("reports a share to one decimal", () => {
    expect(shareOfTotal(250_000, 500_000)).toBe("50.0%");
  });

  it("returns zero rather than NaN when nothing was spent", () => {
    // A period with no spending divides by zero. "NaN%" on a finance screen is
    // worse than a wrong number, because it looks like the app is broken.
    expect(shareOfTotal(0, 0)).toBe("0.0%");
  });
});

describe("isUncategorised", () => {
  it("is the bucket with no category behind it", () => {
    expect(isUncategorised(buckets[1])).toBe(true);
    expect(isUncategorised(buckets[0])).toBe(false);
  });

  it("treats an absent category_id the same as an explicit null", () => {
    // The field is optional in the generated types, so both shapes reach here.
    const missing = { category_name: "Uncategorised", spend_cents: 1 } as Bucket;

    expect(isUncategorised(missing)).toBe(true);
  });
});

describe("CategoryBreakdown", () => {
  it("renders each category with its amount and share", () => {
    render(<CategoryBreakdown buckets={buckets} totalCents={500_000} caption="Spending" />);

    expect(screen.getByText("Housing")).toBeInTheDocument();
    expect(screen.getByText("$2,500.00")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });

  it("gives every bar an accessible name carrying the whole row", () => {
    render(
      <CategoryBreakdown
        buckets={buckets}
        totalCents={500_000}
        caption="Spending"
        onSelect={() => {}}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Housing: $2,500.00, 50.0% of spending, +$100.00 versus the prior period",
      }),
    ).toBeInTheDocument();
  });

  it("reports the selected bucket when a bar is clicked", async () => {
    const onSelect = vi.fn();
    render(
      <CategoryBreakdown
        buckets={buckets}
        totalCents={500_000}
        caption="Spending"
        onSelect={onSelect}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /^Housing/ }));

    expect(onSelect).toHaveBeenCalledWith(buckets[0]);
  });

  it("renders static rows with no buttons when no handler is given", () => {
    render(<CategoryBreakdown buckets={buckets} totalCents={500_000} caption="Spending" />);

    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("survives a negative bucket without drawing a backwards bar", () => {
    // A month whose only Travel row is a refund. The amount still reads correctly.
    const refunded: Bucket[] = [
      { category_id: 24, category_name: "Travel", parent_id: 20, spend_cents: -5_000 },
    ];

    render(<CategoryBreakdown buckets={refunded} totalCents={0} caption="Spending" />);

    expect(screen.getByText("−$50.00")).toBeInTheDocument();
  });
});
