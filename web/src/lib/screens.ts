/**
 * In-app destinations for finding actions and an answer's screen tokens.
 *
 * The contract never carries a URL — an action names a `Screen` and, sometimes, an id —
 * and this is the one function that turns that into a route. A model-authored URL is
 * exactly what the advisor's renderer must never draw, so the mapping lives here, from a
 * fixed enum, and nowhere else. See docs/ADVISOR.md#prompt-injection.
 */

import type { components } from "@/lib/api-types";

export type Screen = components["schemas"]["Screen"];
export type FindingAction = components["schemas"]["FindingAction"];

const ROUTES: Record<Screen, string> = {
  dashboard: "/",
  spending: "/spending",
  transactions: "/transactions",
  accounts: "/accounts",
  account: "/accounts",
  cards: "/cards",
  import: "/import",
  rules: "/rules",
  goals: "/goals",
  planning: "/settings/planning",
  advisor: "/advisor",
};

export const SCREENS = Object.keys(ROUTES) as Screen[];

/** The route for a screen on its own, as an answer's `[[screen:…]]` token names it. */
export function screenRoute(screen: Screen): string {
  return ROUTES[screen];
}

/** The route for a finding's action, using its ids where the screen takes one. */
export function actionRoute(action: Pick<FindingAction, "screen" | "account_id">): string {
  const base = ROUTES[action.screen];
  if (action.screen === "account" && action.account_id) return `${base}/${action.account_id}`;
  if (action.screen === "cards" && action.account_id) return `${base}/${action.account_id}`;
  return base;
}

const ACTION_LABELS: Record<FindingAction["kind"], string> = {
  open: "Open",
  update_balance: "Update balance",
  import_transactions: "Import",
  add_rule: "Add a rule",
  mark_transfer: "Review transactions",
  use_perk: "Open card",
  review: "Review",
};

export function actionLabel(action: Pick<FindingAction, "kind">): string {
  return ACTION_LABELS[action.kind];
}
