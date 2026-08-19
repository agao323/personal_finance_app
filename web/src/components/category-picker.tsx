"use client";

/**
 * Choose a category.
 *
 * A native `<select>` with `<optgroup>`, not a custom combobox. The taxonomy is two
 * levels and about thirty entries — small enough that a popover with its own focus
 * trap, type-ahead, and mobile behaviour would be a lot of machinery to reimplement
 * what the platform already does correctly, including on a phone and with a screen
 * reader.
 *
 * Parents are selectable inside their own group. A transaction genuinely can be
 * categorised as "Food" rather than "Groceries", the spend rollup handles it, and a
 * picker that refused would be describing a rule the data model does not have.
 */

import { useMemo } from "react";

import type { ResponseOf } from "@/lib/api";

export type Category = ResponseOf<"/categories", "get">[number];

/** The empty option's value. `<select>` values are strings; null is not one. */
const NONE = "";

export interface CategoryGroup {
  parent: Category;
  options: Category[];
}

/**
 * Group the flat list into parents and their children.
 *
 * A child whose parent is missing from the list is kept rather than dropped — losing
 * a category silently is worse than showing it ungrouped, and a picker that cannot
 * offer a category makes that category unreachable from the UI entirely.
 */
export function groupCategories(categories: Category[]): {
  groups: CategoryGroup[];
  orphans: Category[];
} {
  const byId = new Map(categories.map((category) => [category.id, category]));
  const groups = new Map<number, CategoryGroup>();
  const orphans: Category[] = [];

  for (const category of categories) {
    if (category.parent_id === null || category.parent_id === undefined) {
      // A parent is selectable in its own right, so it leads its own group.
      groups.set(category.id, { parent: category, options: [category] });
    }
  }

  for (const category of categories) {
    const parentId = category.parent_id;
    if (parentId === null || parentId === undefined) continue;
    const group = groups.get(parentId);
    if (group) group.options.push(category);
    else if (byId.has(parentId)) orphans.push(category);
    else orphans.push(category);
  }

  return { groups: [...groups.values()], orphans };
}

export function CategoryPicker({
  categories,
  value,
  onChange,
  label,
  disabled,
  includeAny,
  className = "",
}: {
  categories: Category[];
  value: number | null;
  onChange: (next: number | null) => void;
  /** Accessible name. Visually hidden — the column header is the visible label. */
  label: string;
  disabled?: boolean;
  /**
   * Filter mode: the empty option means "any category" rather than "no category".
   * The two are opposites, and one label cannot honestly serve both.
   */
  includeAny?: boolean;
  className?: string;
}) {
  const { groups, orphans } = useMemo(() => groupCategories(categories), [categories]);

  return (
    <select
      aria-label={label}
      disabled={disabled}
      value={value === null ? NONE : String(value)}
      onChange={(event) =>
        onChange(event.target.value === NONE ? null : Number(event.target.value))
      }
      className={`border-hairline bg-surface-1 text-ink rounded-md border px-2 py-1 text-sm disabled:opacity-50 ${className}`}
    >
      <option value={NONE}>{includeAny ? "Any category" : "Uncategorised"}</option>
      {groups.map((group) => (
        <optgroup key={group.parent.id} label={group.parent.name}>
          {group.options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </optgroup>
      ))}
      {orphans.length > 0 ? (
        <optgroup label="Other">
          {orphans.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </optgroup>
      ) : null}
    </select>
  );
}
