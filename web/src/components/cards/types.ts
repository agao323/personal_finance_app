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
export type Periods = ResponseOf<"/perks/{perk_id}/periods", "get">;
export type PeriodState = Periods["periods"][number];

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

/**
 * How much history a cadence's grid offers before you ask for more.
 *
 * Per cadence, because twelve chips is a comfortable grid at every cadence but spans a
 * year of months and twelve years of annual credits. Roughly one to three years each:
 * long enough to fill in what you forgot, short enough to read at a glance.
 */
export const PERIODS_BACK: Record<Cadence, number> = {
  monthly: 12,
  quarterly: 8,
  semiannual: 4,
  annual: 3,
};

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/**
 * What to call one period of a perk on this cadence.
 *
 * Named by the calendar unit its **start** falls in — `Jan 2026`, `Q1 2026`, `H1 2026`,
 * `2026` — because that is how the credit is described by the bank and how you remember
 * spending it.
 *
 * A perk anchored mid-month has periods that are not calendar months, and for those the
 * label is an approximation: a quarterly credit anchored 1 February runs February to May
 * and is labelled `Q1 2026`. Labels stay distinct and in order, which is what a grid needs,
 * and every chip also carries its exact half-open range in its accessible name, so nothing
 * depends on the label being more precise than it is.
 *
 * Parsed from the ISO string rather than through `Date`, which would shift the day in any
 * timezone behind UTC and could move a period into the wrong month.
 */
export function periodLabel(cadence: Cadence, start: string): string {
  const [year, month] = start.split("-").map(Number);
  switch (cadence) {
    case "monthly":
      return `${MONTHS[month - 1]} ${year}`;
    case "quarterly":
      return `Q${Math.floor((month - 1) / 3) + 1} ${year}`;
    case "semiannual":
      return `H${month <= 6 ? 1 : 2} ${year}`;
    case "annual":
      return String(year);
  }
}
