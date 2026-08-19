import { describe, expect, it } from "vitest";

import {
  computeDelta,
  formatAge,
  formatBps,
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatSignedCurrency,
  centsToInputValue,
  parseDollarsToCents,
} from "@/lib/format";

const MINUS = "−";

describe("formatCurrency", () => {
  it.each([
    [0, "$0.00"],
    [1, "$0.01"],
    [99, "$0.99"],
    [100, "$1.00"],
    [123_456, "$1,234.56"],
    [100_000_000, "$1,000,000.00"],
  ])("formats %i cents as %s", (cents, expected) => {
    expect(formatCurrency(cents)).toBe(expected);
  });

  it("uses a typographic minus for negatives", () => {
    expect(formatCurrency(-123_456)).toBe(`${MINUS}$1,234.56`);
  });

  it("pads a single-digit cent value", () => {
    // The bug this catches renders 1205 as "$12.5" rather than "$12.05".
    expect(formatCurrency(1205)).toBe("$12.05");
  });

  it("handles values beyond a 32-bit integer", () => {
    expect(formatCurrency(999_999_999_999)).toBe("$9,999,999,999.99");
  });

  it("stays exact where floating point would not", () => {
    // 0.1 + 0.2 !== 0.3 in a double. Splitting the integer avoids the question.
    expect(formatCurrency(10 + 20)).toBe("$0.30");
    expect(formatCurrency(70)).toBe("$0.70");
    expect(formatCurrency(1_000_000_01)).toBe("$1,000,000.01");
  });

  it("rounds half-up when cents are hidden", () => {
    expect(formatCurrency(1_250, { showCents: false })).toBe("$13");
    expect(formatCurrency(1_249, { showCents: false })).toBe("$12");
  });

  it("signs positives only when asked, and never signs zero", () => {
    expect(formatCurrency(500, { signed: true })).toBe("+$5.00");
    expect(formatCurrency(0, { signed: true })).toBe("$0.00");
    expect(formatCurrency(500)).toBe("$5.00");
  });

  it("rejects a fractional value rather than silently rounding", () => {
    // A non-integer here means something already divided by 100 upstream.
    expect(() => formatCurrency(12.5)).toThrow(/integer cents/);
  });

  it("rejects NaN and Infinity", () => {
    expect(() => formatCurrency(NaN)).toThrow(/finite/);
    expect(() => formatCurrency(Infinity)).toThrow(/finite/);
  });
});

describe("formatCompactCurrency", () => {
  it.each([
    [0, "$0"],
    [123_456, "$1,235"],
    [999_999_99, "$1M"],
    [1_000_000_00, "$1M"],
    [4_200_000_00, "$4.2M"],
    [12_345_00, "$12.3K"],
  ])("formats %i cents as %s", (cents, expected) => {
    expect(formatCompactCurrency(cents)).toBe(expected);
  });

  it("falls back to whole dollars below $10,000", () => {
    // Compacting saves nothing here and loses precision.
    expect(formatCompactCurrency(999_900)).toBe("$9,999");
  });

  it("uses a typographic minus for negatives", () => {
    expect(formatCompactCurrency(-4_200_000_00)).toBe(`${MINUS}$4.2M`);
  });
});

describe("formatSignedCurrency", () => {
  it.each([
    [1_234_56, "+$1,234.56"],
    [-1_234_56, `${MINUS}$1,234.56`],
    [0, "$0.00"],
  ])("formats %i cents as %s", (cents, expected) => {
    expect(formatSignedCurrency(cents)).toBe(expected);
  });
});

describe("formatBps", () => {
  it.each([
    [10_000, "100%"],
    [5_000, "50%"],
    [3_333, "33.33%"],
    [1, "0.01%"],
    [0, "0%"],
    [2_550, "25.5%"],
  ])("formats %i bps as %s", (bps, expected) => {
    expect(formatBps(bps)).toBe(expected);
  });

  it("drops trailing zeros so a round stake does not look over-precise", () => {
    expect(formatBps(5_000)).toBe("50%");
    expect(formatBps(5_050)).toBe("50.5%");
  });

  it("rejects a fractional basis point", () => {
    expect(() => formatBps(50.5)).toThrow(/integer/);
  });
});

describe("computeDelta", () => {
  it("reports direction, absolute, and percentage change", () => {
    const delta = computeDelta(110_000, 100_000);

    expect(delta.direction).toBe("up");
    expect(delta.absolute).toBe("+$100.00");
    expect(delta.percent).toBe("+10.0%");
  });

  it("handles a decrease", () => {
    const delta = computeDelta(90_000, 100_000);

    expect(delta.direction).toBe("down");
    expect(delta.absolute).toBe(`${MINUS}$100.00`);
    expect(delta.percent).toBe(`${MINUS}10.0%`);
  });

  it("reports flat when nothing changed", () => {
    const delta = computeDelta(100_000, 100_000);

    expect(delta.direction).toBe("flat");
    expect(delta.absolute).toBe("$0.00");
    // Unsigned, matching formatCurrency: zero is neither a gain nor a loss.
    expect(delta.percent).toBe("0.0%");
  });

  it("returns no percentage when the prior period was zero", () => {
    // Going from nothing to something is not a percentage. Infinity on a
    // dashboard is worse than an absent number.
    const delta = computeDelta(50_000, 0);

    expect(delta.percent).toBeNull();
    expect(delta.absolute).toBe("+$500.00");
  });

  it("returns no percentage when the prior period was negative", () => {
    // "Improved by −140%" is not a sentence anyone can act on.
    expect(computeDelta(50_000, -20_000).percent).toBeNull();
  });

  it("rounds the percentage to one decimal place", () => {
    expect(computeDelta(100_333, 100_000).percent).toBe("+0.3%");
  });
});

describe("formatDate", () => {
  it("formats an ISO date without shifting timezone", () => {
    // Naive parsing turns 2026-01-01 into 2025-12-31 west of UTC.
    expect(formatDate("2026-01-01")).toBe("Jan 1, 2026");
    expect(formatDate("2026-08-18")).toBe("Aug 18, 2026");
  });
});

describe("formatAge", () => {
  const now = new Date("2026-08-18T00:00:00Z");

  it.each([
    ["2026-08-18", "today"],
    ["2026-08-17", "yesterday"],
    ["2026-08-11", "7 days ago"],
    ["2026-07-18", "1 month ago"],
    ["2026-05-18", "3 months ago"],
    ["2025-08-18", "1 year ago"],
  ])("describes %s as %s", (iso, expected) => {
    expect(formatAge(iso, now)).toBe(expected);
  });
});

describe("parseDollarsToCents", () => {
  it("converts a plain amount exactly", () => {
    // parseFloat("12.34") * 100 is 1233.9999999999998. This is why the string is
    // split rather than multiplied.
    expect(parseDollarsToCents("12.34")).toBe(1234);
  });

  it("handles whole dollars and a bare decimal point", () => {
    expect(parseDollarsToCents("12")).toBe(1200);
    expect(parseDollarsToCents("12.")).toBe(1200);
    expect(parseDollarsToCents(".50")).toBe(50);
  });

  it("pads a single decimal place", () => {
    expect(parseDollarsToCents("12.3")).toBe(1230);
  });

  it("strips currency decoration people actually type", () => {
    expect(parseDollarsToCents("$1,234.56")).toBe(123_456);
  });

  it("rounds a half cent away from zero, matching the server", () => {
    // ROUND_HALF_UP in services/ownership.py. Rounding differently here is how a
    // total ends up disagreeing with the row that produced it.
    expect(parseDollarsToCents("12.345")).toBe(1235);
    expect(parseDollarsToCents("-12.345")).toBe(-1235);
  });

  it("rounds below a half cent down", () => {
    expect(parseDollarsToCents("12.344")).toBe(1234);
    expect(parseDollarsToCents("12.3449999")).toBe(1234);
  });

  it("keeps the sign on a negative", () => {
    expect(parseDollarsToCents("-0.05")).toBe(-5);
  });

  it("returns null for anything that is not a number", () => {
    // Null lets the form say so. A silent zero is a balance claim.
    expect(parseDollarsToCents("")).toBeNull();
    expect(parseDollarsToCents("abc")).toBeNull();
    expect(parseDollarsToCents("-")).toBeNull();
    expect(parseDollarsToCents("1.2.3")).toBeNull();
  });

  it("refuses an amount too large to be exact", () => {
    expect(parseDollarsToCents("999999999999999999999")).toBeNull();
  });
});

describe("centsToInputValue", () => {
  it("round-trips through parseDollarsToCents", () => {
    for (const cents of [0, 5, 100, 123_456, -4_512]) {
      expect(parseDollarsToCents(centsToInputValue(cents))).toBe(cents);
    }
  });

  it("keeps both decimal places", () => {
    expect(centsToInputValue(1200)).toBe("12.00");
    expect(centsToInputValue(5)).toBe("0.05");
  });
});
