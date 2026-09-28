/**
 * Goals, as the screens word them. One place for the labels and the target sentence, so the
 * goals list and the Spending screen say the same thing about the same goal.
 */

import type { ResponseOf } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatCurrency, formatDate } from "@/lib/format";

export type Goal = ResponseOf<"/goals", "get">[number];
export type GoalKind = components["schemas"]["GoalKind"];
export type GoalCreate = components["schemas"]["GoalCreate"];
export type GoalUpdate = components["schemas"]["GoalUpdate"];

export const KIND_LABELS: Record<GoalKind, string> = {
  spending_limit: "Spending limit",
  emergency_fund: "Emergency fund",
  savings_target: "Savings target",
};

/** `60` tenths → `6.0 months`. Integer arithmetic; no float touches the figure. */
export function formatMonthsTenths(tenths: number): string {
  const whole = Math.trunc(tenths / 10);
  const rest = Math.abs(tenths % 10);
  return `${whole}.${rest} months`;
}

/** Parse "6" or "6.5" months into tenths; null for anything else. */
export function parseMonthsToTenths(input: string): number | null {
  const match = input.trim().match(/^(\d{1,3})(?:\.(\d))?$/);
  if (!match) return null;
  return Number(match[1]) * 10 + Number(match[2] ?? "0");
}

/** What the goal is aiming for, in one line. */
export function describeTarget(goal: Goal, accountNames: Map<number, string> = new Map()): string {
  switch (goal.kind) {
    case "spending_limit":
      return `${formatCurrency(goal.target_amount_cents ?? 0)} a month on ${goal.category_name ?? "a category"}`;
    case "emergency_fund":
      return `${formatMonthsTenths(goal.target_months_tenths ?? 0)} of spending in cash`;
    case "savings_target": {
      const by = goal.target_date ? ` by ${formatDate(goal.target_date)}` : "";
      const from = goal.account_ids.map((id) => accountNames.get(id) ?? `account ${id}`).join(", ");
      return `${formatCurrency(goal.target_amount_cents ?? 0)}${by}${from ? `, from ${from}` : ""}`;
    }
  }
}
