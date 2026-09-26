/**
 * Shared shapes for the cards screen, derived from the generated contract.
 *
 * One place, so five component files cannot disagree about what a perk is. Everything
 * here comes from `api-types.ts`, which is generated from the Pydantic models — there is
 * no hand-written mirror of a response shape anywhere in this directory.
 */

import type { components } from "@/lib/api-types";
import type { ResponseOf } from "@/lib/api";

export type Cards = ResponseOf<"/cards", "get">;
export type Card = Cards[number];
export type Perk = Card["perks"][number];
export type PerkPeriod = NonNullable<Perk["current_period"]>;
export type Upcoming = ResponseOf<"/perks/upcoming", "get">;
export type History = ResponseOf<"/cards/history", "get">;
export type Redemption = History["redemptions"][number];
export type Cadence = components["schemas"]["PerkCadence"];

/** Monthly first: it recurs most often and so gets checked most often. */
export const CADENCE_ORDER: readonly Cadence[] = ["monthly", "quarterly", "semiannual", "annual"];

export const CADENCE_LABELS: Record<Cadence, string> = {
  monthly: "Monthly",
  quarterly: "Quarterly",
  semiannual: "Every 6 months",
  annual: "Annual",
};

/**
 * How soon a deadline reads.
 *
 * "Expires in 0 days" is the sentence nobody parses at a glance, and it is the one that
 * matters most — `days_remaining` is 0 on the final day.
 *
 * Deliberately says nothing about whether this is *urgent*. That depends on the cadence
 * and the API decides it; this only phrases a number.
 */
export function expiryLabel(daysRemaining: number): string {
  if (daysRemaining <= 0) return "Today";
  if (daysRemaining === 1) return "Tomorrow";
  if (daysRemaining < 7) return `${daysRemaining} days`;
  if (daysRemaining < 14) return "Next week";
  return `${daysRemaining} days`;
}
