"use client";

/**
 * Insights: what needs attention, from the findings engine. No model is involved.
 *
 * **Settled findings stay on screen while refetching.** Switching Mine / Household, or
 * coming back to the dashboard, never collapses the panel to a skeleton once findings
 * have arrived — a quiet "Refreshing" mark sits beside them instead (the ticket 070
 * pattern). The owner reads this on a phone in short visits, and a panel that resets for
 * a one-toggle change costs them their place.
 *
 * The server's order is kept: severity, then money at stake. Nothing here re-sorts.
 */

import { useEffect, useState } from "react";

import { FindingRow, type Finding } from "@/components/insights/finding-row";
import { ErrorState, Refreshing, Skeleton } from "@/components/states";
import type { ViewScope } from "@/components/view-toggle";
import { apiFetch } from "@/lib/api";

/** How many findings show before "Show all". */
export const COLLAPSED = 5;

type Loaded = { view: ViewScope; findings: Finding[] };

export function InsightsPanel({ view }: { view: ViewScope }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let live = true;
    apiFetch("/insights", { query: { view } })
      .then((body) => {
        if (!live) return;
        setLoaded({ view, findings: body.findings });
        setError(null);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, [view]);

  if (loaded === null) {
    if (error) return <ErrorState title="Insights unavailable" detail={error} />;
    return (
      <section aria-label="Insights" className="border-hairline bg-surface-1 rounded-xl border p-4">
        <h2 className="text-ink-secondary text-sm">Insights</h2>
        <Skeleton className="mt-3 h-12 w-full" />
      </section>
    );
  }

  const refreshing = loaded.view !== view && error === null;
  const shown = expanded ? loaded.findings : loaded.findings.slice(0, COLLAPSED);
  const hidden = loaded.findings.length - shown.length;

  return (
    <section aria-label="Insights" className="border-hairline bg-surface-1 rounded-xl border p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-ink-secondary text-sm">Insights</h2>
        {refreshing ? <Refreshing /> : null}
      </div>

      {error ? <p className="text-critical-text mt-2 text-sm">Could not refresh: {error}</p> : null}

      {loaded.findings.length === 0 ? (
        <p className="text-ink-secondary mt-3 text-sm">Nothing needs attention.</p>
      ) : (
        <ul className="mt-1">
          {shown.map((finding) => (
            <FindingRow key={finding.id} finding={finding} />
          ))}
        </ul>
      )}

      {hidden > 0 || expanded ? (
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          className="text-accent-strong mt-2 text-sm hover:underline"
        >
          {expanded ? "Show fewer" : `Show all (${loaded.findings.length})`}
        </button>
      ) : null}
    </section>
  );
}
