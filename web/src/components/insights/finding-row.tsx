"use client";

/**
 * One finding: what, how urgent, on what evidence, and where to act on it.
 *
 * The title and detail are server-rendered text that can contain imported strings — a
 * merchant name from a bank export. They are rendered as **text**, never markdown or
 * HTML; React escapes them, and nothing here parses them.
 *
 * The action sits on the finding it acts on, not in the panel header: the owner looks
 * for a control where its subject is.
 */

import Link from "next/link";

import type { components } from "@/lib/api-types";
import { formatBps, formatCurrency, formatDate } from "@/lib/format";
import { actionLabel, actionRoute } from "@/lib/screens";

export type Finding = components["schemas"]["Finding"];
type Evidence = components["schemas"]["Evidence"];

const SEVERITY: Record<Finding["severity"], { label: string; dot: string }> = {
  urgent: { label: "Urgent", dot: "bg-critical" },
  warning: { label: "Warning", dot: "bg-serious" },
  notice: { label: "Notice", dot: "bg-warning" },
  info: { label: "Info", dot: "bg-accent" },
};

/** `234` tenths → `23.4 months`, in integer arithmetic. */
function formatMonthsTenths(tenths: number): string {
  const negative = tenths < 0;
  const absolute = Math.abs(tenths);
  return `${negative ? "−" : ""}${Math.floor(absolute / 10)}.${absolute % 10} months`;
}

export function formatEvidence(evidence: Evidence): string {
  switch (evidence.unit) {
    case "cents":
      return evidence.value_cents == null ? "—" : formatCurrency(evidence.value_cents);
    case "bps":
      return evidence.value_bps == null ? "—" : formatBps(evidence.value_bps);
    case "months_tenths":
      return evidence.value_months_tenths == null
        ? "—"
        : formatMonthsTenths(evidence.value_months_tenths);
    case "date":
      return evidence.value_date ? formatDate(evidence.value_date) : "—";
    case "days":
      return evidence.value_count == null
        ? "—"
        : `${evidence.value_count} day${evidence.value_count === 1 ? "" : "s"}`;
    default:
      return evidence.value_count == null ? "—" : String(evidence.value_count);
  }
}

export function FindingRow({ finding }: { finding: Finding }) {
  const severity = SEVERITY[finding.severity];

  return (
    <li className="border-hairline flex flex-col gap-2 border-t py-3 first:border-t-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${severity.dot}`} />
          <span className="sr-only">{severity.label}: </span>
          <span className="min-w-0">{finding.title}</span>
          {finding.stale ? (
            <span className="bg-warning-bg text-warning-text rounded px-1.5 py-0.5 text-[11px] font-normal">
              Stale balance
            </span>
          ) : null}
        </p>
        <p className="text-ink-secondary mt-1 text-sm">{finding.detail}</p>
        <dl className="text-ink-muted mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {finding.evidence.map((evidence, index) => (
            <div key={`${evidence.label}-${index}`} className="flex gap-1">
              <dt>{evidence.label}</dt>
              <dd className="text-ink-secondary tabular-nums">{formatEvidence(evidence)}</dd>
            </div>
          ))}
        </dl>
      </div>
      {finding.action ? (
        <Link
          href={actionRoute(finding.action)}
          className="border-hairline text-ink hover:bg-surface-2 shrink-0 self-start rounded-md border px-2.5 py-1 text-sm"
        >
          {actionLabel(finding.action)}
        </Link>
      ) : null}
    </li>
  );
}
