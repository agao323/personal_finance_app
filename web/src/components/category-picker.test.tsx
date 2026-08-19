import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CategoryPicker, groupCategories, type Category } from "@/components/category-picker";
import { categories } from "@/test/msw";

describe("groupCategories", () => {
  it("puts each parent at the head of its own group", () => {
    const { groups } = groupCategories(categories);
    const food = groups.find((group) => group.parent.name === "Food")!;

    // The parent is selectable in its own right — a transaction genuinely can be
    // categorised "Food" rather than "Groceries".
    expect(food.options.map((option) => option.name)).toEqual(["Food", "Groceries", "Restaurants"]);
  });

  it("keeps income and transfer groups, not only expenses", () => {
    const { groups } = groupCategories(categories);

    expect(groups.map((group) => group.parent.name)).toEqual([
      "Housing",
      "Food",
      "Income",
      "Transfer",
    ]);
  });

  it("keeps a child whose parent is missing rather than dropping it", () => {
    // A dropped category is unreachable from the UI entirely, which is worse than
    // one shown without its group.
    const orphaned: Category[] = [{ id: 99, name: "Stray", parent_id: 404, kind: "expense" }];

    const { orphans } = groupCategories(orphaned);

    expect(orphans.map((option) => option.name)).toEqual(["Stray"]);
  });

  it("returns nothing for an empty taxonomy", () => {
    expect(groupCategories([])).toEqual({ groups: [], orphans: [] });
  });
});

describe("CategoryPicker", () => {
  it("labels the empty option 'Uncategorised' when assigning", () => {
    render(
      <CategoryPicker label="Category" categories={categories} value={null} onChange={() => {}} />,
    );

    expect(screen.getByRole("option", { name: "Uncategorised" })).toBeInTheDocument();
  });

  it("labels the empty option 'Any category' when filtering", () => {
    // Assigning nothing and matching anything are opposites; one label cannot
    // honestly serve both.
    render(
      <CategoryPicker
        label="Category"
        includeAny
        categories={categories}
        value={null}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("option", { name: "Any category" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Uncategorised" })).not.toBeInTheDocument();
  });

  it("reports the chosen category as a number", async () => {
    const onChange = vi.fn();
    render(
      <CategoryPicker label="Category" categories={categories} value={null} onChange={onChange} />,
    );

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "11");

    expect(onChange).toHaveBeenCalledWith(11);
  });

  it("reports null when the empty option is chosen", async () => {
    const onChange = vi.fn();
    render(
      <CategoryPicker label="Category" categories={categories} value={11} onChange={onChange} />,
    );

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Category" }), "");

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("can be disabled while a write is in flight", () => {
    render(
      <CategoryPicker
        label="Category"
        disabled
        categories={categories}
        value={11}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("combobox", { name: "Category" })).toBeDisabled();
  });
});
