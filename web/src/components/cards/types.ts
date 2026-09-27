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
export type Schedule = ResponseOf<"/perks/schedule", "get">;
export type PeriodState = Periods["periods"][number];

/** Monthly first: it recurs most often and so gets checked most often. */
export const CADENCE_ORDER: readonly Cadence[] = ["monthly", "quarterly", "semiannual", "annual"];

/** What a calendar-aligned schedule is called, per cadence. Ticket 079. */
export const CALENDAR_LABELS: Record<Cadence, string> = {
  monthly: "Calendar months",
  quarterly: "Calendar quarters",
  semiannual: "Calendar halves",
  annual: "Calendar year",
};

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

/**
 * What one period of each cadence is called, for copy that has to name it.
 *
 * "Tap a month" is wrong on a quarterly credit, and "tap a period" is a word nobody uses
 * about their own credit card.
 */
export const PERIOD_NOUN: Record<Cadence, { one: string; many: string }> = {
  monthly: { one: "month", many: "months" },
  quarterly: { one: "quarter", many: "quarters" },
  semiannual: { one: "half year", many: "half years" },
  annual: { one: "year", many: "years" },
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

/**
 * A window over history, named for the calendar period it covers. (Ticket 071)
 *
 * The credits themselves run on calendar periods, so the windows for reading them back do
 * too: "this quarter" is the unit a quarterly credit is described in, where "3 months back"
 * is a unit nothing is described in.
 */
export type HistoryWindow = "month" | "quarter" | "half" | "year" | "all";

export const HISTORY_WINDOWS: readonly { id: HistoryWindow; label: string }[] = [
  { id: "month", label: "This month" },
  { id: "quarter", label: "This quarter" },
  { id: "half", label: "This half year" },
  { id: "year", label: "This year" },
  // Last, and the default. No silent cut-off: "show me everything" is the request the
  // panel answers, and a window it narrowed to on its own would hide exactly the old
  // entries being asked for.
  { id: "all", label: "All time" },
];

/**
 * When a window begins, as an ISO date, or null for all time.
 *
 * Plain calendar arithmetic, deliberately: these are boundaries of months and quarters,
 * not of any perk's periods, so there is nothing here that could disagree with
 * `services/perks.py`. A window over a *perk's* own periods would have to come from the
 * API, and does — see `period-grid.tsx`.
 *
 * UTC throughout, matching `formatDate` and the ISO dates the API speaks.
 */
export function calendarWindowStart(window: HistoryWindow, today: Date): string | null {
  if (window === "all") return null;
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();
  const firstOf = (m: number) => new Date(Date.UTC(year, m, 1)).toISOString().slice(0, 10);
  switch (window) {
    case "month":
      return firstOf(month);
    case "quarter":
      return firstOf(Math.floor(month / 3) * 3);
    case "half":
      return firstOf(month < 6 ? 0 : 6);
    case "year":
      return firstOf(0);
  }
}
