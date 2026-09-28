"use client";

/**
 * Whether a question can be asked right now, and if not, why — never a vague "unavailable".
 *
 * When the advisor is off for any reason, the Insights panel is named as the thing that still
 * works: it never calls a model, so the budget, the switch and the demo do not touch it.
 */

import Link from "next/link";

import { REASONS, type AdvisorStatus } from "@/lib/advisor";
import { formatCurrency, formatDate } from "@/lib/format";

export function StatusLine({ status }: { status: AdvisorStatus }) {
  if (status.enabled) {
    return (
      <p className="text-ink-secondary text-sm">
        Ready. This month: {formatCurrency(status.month_spent_cents)} of{" "}
        {formatCurrency(status.month_cap_cents, { showCents: false })}.
      </p>
    );
  }

  const reason = status.reason ?? "disabled";
  return (
    <div role="status" className="border-hairline bg-surface-2 rounded-lg border px-3 py-2 text-sm">
      <p className="text-ink">
        {REASONS[reason]}
        {reason === "monthly_cap" ? ` It resets on ${formatDate(status.resets_on)}.` : null}
      </p>
      <p className="text-ink-secondary mt-1">
        <Link href="/" className="text-accent-strong hover:underline">
          Insights on the dashboard
        </Link>{" "}
        still work — they never ask a model.
      </p>
    </div>
  );
}
