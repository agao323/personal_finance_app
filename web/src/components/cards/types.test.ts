/**
 * The label on a period chip. (Ticket 069)
 *
 * Hand-computed, including the cases where a perk's periods are not calendar-aligned —
 * those are the ones a label can only approximate, and the test is here to record that it
 * approximates them predictably rather than confusingly.
 */

import { describe, expect, it } from "vitest";

import { PERIODS_BACK, periodLabel } from "@/components/cards/types";

describe("periodLabel", () => {
  it("names a month", () => {
    expect(periodLabel("monthly", "2026-01-01")).toBe("Jan 2026");
    expect(periodLabel("monthly", "2026-12-01")).toBe("Dec 2026");
  });

  it("names a quarter by the quarter its start falls in", () => {
    expect(periodLabel("quarterly", "2026-01-01")).toBe("Q1 2026");
    expect(periodLabel("quarterly", "2026-04-01")).toBe("Q2 2026");
    expect(periodLabel("quarterly", "2026-07-01")).toBe("Q3 2026");
    expect(periodLabel("quarterly", "2026-10-01")).toBe("Q4 2026");
  });

  it("names a half year", () => {
    expect(periodLabel("semiannual", "2026-01-01")).toBe("H1 2026");
    expect(periodLabel("semiannual", "2026-06-01")).toBe("H1 2026");
    expect(periodLabel("semiannual", "2026-07-01")).toBe("H2 2026");
  });

  it("names a year", () => {
    expect(periodLabel("annual", "2026-03-15")).toBe("2026");
  });

  it("stays distinct and in order for periods that are not calendar-aligned", () => {
    // A quarterly credit anchored 1 February runs Feb–May, May–Aug, Aug–Nov, Nov–Feb.
    // The labels are an approximation — Feb is in Q1 — but consecutive periods never
    // collide, which is what a grid of chips actually needs.
    const starts = ["2026-02-01", "2026-05-01", "2026-08-01", "2026-11-01"];
    const labels = starts.map((start) => periodLabel("quarterly", start));

    expect(labels).toEqual(["Q1 2026", "Q2 2026", "Q3 2026", "Q4 2026"]);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("reads the month from the string rather than through a Date", () => {
    // `new Date("2026-03-01")` is midnight UTC, which is 28 February anywhere behind it.
    // Parsing the string cannot drift.
    expect(periodLabel("monthly", "2026-03-01")).toBe("Mar 2026");
  });
});

describe("PERIODS_BACK", () => {
  it("offers between one and three years of history at every cadence", () => {
    // The grid has to be readable at a glance and long enough to fill in what you forgot.
    const years = { monthly: 1 / 12, quarterly: 1 / 4, semiannual: 1 / 2, annual: 1 };
    for (const [cadence, months] of Object.entries(years)) {
      const span = PERIODS_BACK[cadence as keyof typeof years] * months;
      expect(span).toBeGreaterThanOrEqual(1);
      expect(span).toBeLessThanOrEqual(3);
    }
  });
});
