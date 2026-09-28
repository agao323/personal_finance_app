/**
 * Planning assumptions, as the settings screen reads and writes them.
 *
 * Every rate and the target mix travel as basis points (4000 is 40.00%). A person types
 * percentages; these convert between the two with string arithmetic, never a float, for the
 * same reason money never touches one.
 */

import type { ResponseOf } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Assumptions = ResponseOf<"/planning/assumptions", "get">[number];
export type AssumptionsCreate = components["schemas"]["AssumptionsCreate"];
export type RiskTolerance = components["schemas"]["RiskTolerance"];

export const MIX_FIELDS = [
  ["target_us_equity_bps", "US stocks"],
  ["target_intl_equity_bps", "International stocks"],
  ["target_bonds_bps", "Bonds"],
  ["target_cash_bps", "Cash"],
  ["target_other_bps", "Other"],
] as const;

export type MixField = (typeof MIX_FIELDS)[number][0];

/** "5", "5.2", "5.25", "-1.5" → basis points; null for anything else. */
export function parsePercentToBps(input: string): number | null {
  const match = input.trim().match(/^(-)?(\d{1,3})(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  const hundredths = Number((match[3] ?? "").padEnd(2, "0"));
  const bps = Number(match[2]) * 100 + hundredths;
  return match[1] ? -bps : bps;
}

/** Basis points → the text a person would type: 500 → "5", 525 → "5.25", 450 → "4.5". */
export function bpsToInput(bps: number): string {
  const sign = bps < 0 ? "-" : "";
  const absolute = Math.abs(bps);
  const whole = Math.trunc(absolute / 100);
  const rest = absolute % 100;
  if (rest === 0) return `${sign}${whole}`;
  return `${sign}${whole}.${String(rest).padStart(2, "0").replace(/0$/, "")}`;
}

/** The mix's total, or null while any part is not a number. */
export function mixTotal(values: Record<MixField, string>): number | null {
  let total = 0;
  for (const [field] of MIX_FIELDS) {
    const bps = parsePercentToBps(values[field]);
    if (bps === null) return null;
    total += bps;
  }
  return total;
}
