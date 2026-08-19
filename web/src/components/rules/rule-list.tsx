"use client";

/**
 * The rule set, in the order it runs.
 *
 * Order is the whole semantics: lower priority runs first and the first match wins,
 * so a broad "contains AMZN" above a narrow "contains AMZN MKTP" makes the narrow one
 * unreachable. The list is numbered and the arrows move a rule through that order,
 * because a rule set you cannot reorder is one you have to delete and retype to fix.
 *
 * Explicit up/down buttons rather than drag. Drag needs a pointer, a keyboard
 * alternative, and a live region to announce the result — three implementations of
 * one affordance, for a list that is a dozen rows long and reordered rarely.
 */

import type { Rule } from "@/components/rules/rule-form";
import { MATCH_TYPES } from "@/components/rules/rule-form";

/**
 * The two rules whose priorities a move swaps.
 *
 * Returns null at the ends rather than clamping silently — the caller disables the
 * button, and a "move" that does nothing is worse than one that is visibly absent.
 */
export function swapTarget(
  rules: Rule[],
  id: number,
  direction: "up" | "down",
): { rule: Rule; other: Rule } | null {
  const index = rules.findIndex((rule) => rule.id === id);
  if (index === -1) return null;
  const otherIndex = direction === "up" ? index - 1 : index + 1;
  if (otherIndex < 0 || otherIndex >= rules.length) return null;
  return { rule: rules[index], other: rules[otherIndex] };
}

/** Run order: priority, then id — total and deterministic, matching the engine. */
export function inRunOrder(rules: Rule[]): Rule[] {
  return [...rules].sort((a, b) => a.priority - b.priority || a.id - b.id);
}

const MATCH_LABELS = new Map(MATCH_TYPES.map((option) => [option.value, option.label]));

export function RuleList({
  rules,
  busyId,
  onEdit,
  onDelete,
  onMove,
}: {
  rules: Rule[];
  busyId: number | null;
  onEdit: (rule: Rule) => void;
  onDelete: (rule: Rule) => void;
  onMove: (rule: Rule, direction: "up" | "down") => void;
}) {
  const ordered = inRunOrder(rules);

  return (
    <ol className="mt-3">
      {ordered.map((rule, index) => (
        <li
          key={rule.id}
          className={`border-hairline/60 flex flex-wrap items-center gap-3 border-b py-2 last:border-0 ${
            busyId === rule.id ? "opacity-50" : ""
          }`}
        >
          <span className="text-ink-muted w-6 text-sm tabular-nums">{index + 1}</span>

          <span className="min-w-0 flex-1 text-sm">
            <span className="text-ink-secondary">{MATCH_LABELS.get(rule.match_type)}</span>{" "}
            <span className="font-medium">{rule.pattern}</span>
            <span className="text-ink-secondary"> → </span>
            <span className="font-medium">{rule.category_name}</span>
          </span>

          <span className="flex items-center gap-1">
            <button
              type="button"
              aria-label={`Move ${rule.pattern} earlier`}
              disabled={index === 0 || busyId !== null}
              onClick={() => onMove(rule, "up")}
              className="border-hairline hover:bg-surface-2 rounded-md border px-2 py-1 text-xs disabled:opacity-30"
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={`Move ${rule.pattern} later`}
              disabled={index === ordered.length - 1 || busyId !== null}
              onClick={() => onMove(rule, "down")}
              className="border-hairline hover:bg-surface-2 rounded-md border px-2 py-1 text-xs disabled:opacity-30"
            >
              ↓
            </button>
            <button
              type="button"
              onClick={() => onEdit(rule)}
              className="text-ink-secondary hover:text-ink px-2 py-1 text-sm underline underline-offset-4"
            >
              Edit
            </button>
            <button
              type="button"
              aria-label={`Delete ${rule.pattern}`}
              onClick={() => onDelete(rule)}
              className="text-critical-text px-2 py-1 text-sm underline underline-offset-4"
            >
              Delete
            </button>
          </span>
        </li>
      ))}
    </ol>
  );
}
