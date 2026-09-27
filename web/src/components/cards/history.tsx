"use client";

/**
 * Everything you have ever marked. (Tickets 058, 069, 070)
 *
 * **No default cut-off.** "Show me the whole history" is the request this answers, and a
 * silent window would hide exactly the old entries being asked for. The window control
 * narrows; it never widens from a default that was already narrow.
 *
 * Recording a use you forgot lives in `period-grid.tsx`, next to the credit it belongs to.
 * This panel reads history; it no longer writes it.
 */

import { useEffect, useState } from "react";

import { ErrorState, Refreshing, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { CADENCE_LABELS, type Cadence, type History } from "./types";

const WINDOWS = [
  { months: 0, label: "All time" },
  { months: 3, label: "3 months" },
  { months: 12, label: "12 months" },
] as const;

/** `months` back from today, as an ISO date. UTC throughout, matching `formatDate`. */
function isoMonthsAgo(months: number): string {
  const now = new Date();
  const target = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - months, 1));
  return target.toISOString().slice(0, 10);
}

export function HistoryPanel({
  revision,
  accountId,
}: {
  revision: number;
  /** Scope to one card. Omitted means the whole wallet. */
  accountId?: number;
}) {
  const [months, setMonths] = useState(0);
  const [loaded, setLoaded] = useState<{
    key: string;
    data: History | null;
    error: string | null;
  } | null>(null);

  // Derived, not a flag set at the top of the effect — see the note in `upcoming.tsx`.
  //
  // Ticket 070: the window switcher was the worst offender. Every change of window blanked
  // the totals and the whole list and rebuilt them, for a request that usually answers in
  // under a tenth of a second. The rows in hand stay up while the next ones load.
  const key = `${months}|${revision}|${accountId ?? "all"}`;
  const data = loaded?.data ?? null;
  const pending = loaded === null;
  const refreshing = loaded !== null && loaded.key !== key;
  const error = loaded?.error ?? null;

  useEffect(() => {
    let live = true;
    const requested = `${months}|${revision}|${accountId ?? "all"}`;
    apiFetch("/cards/history", {
      query: {
        ...(months === 0 ? {} : { from: isoMonthsAgo(months) }),
        ...(accountId === undefined ? {} : { account_id: accountId }),
      },
    })
      .then((next) => {
        if (live) setLoaded({ key: requested, data: next, error: null });
      })
      .catch((cause: unknown) => {
        if (live)
          // Keep the rows already on screen; a failed refresh has not made them wrong.
          setLoaded((previous) => ({
            key: requested,
            data: previous?.data ?? null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          }));
      });
    return () => {
      live = false;
    };
  }, [months, revision, accountId]);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="flex items-baseline gap-2 text-sm font-medium">
          What you have used
          {refreshing ? <Refreshing /> : null}
        </h2>
        <div role="group" aria-label="How far back" className="flex flex-wrap gap-1">
          {WINDOWS.map((option) => (
            <button
              key={option.months}
              type="button"
              aria-pressed={months === option.months}
              onClick={() => setMonths(option.months)}
              className={`rounded-md px-2 py-1 text-xs transition-colors ${
                months === option.months
                  ? "bg-accent-bg text-accent-strong font-medium"
                  : "text-ink-secondary hover:text-ink"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error && data === null ? <ErrorState detail={error} /> : null}
      {error && data !== null ? (
        <p role="alert" className="text-critical-text mt-1 text-xs">
          Could not refresh that window.
        </p>
      ) : null}

      {pending && !error ? (
        <Skeleton className="mt-3 h-24 w-full" />
      ) : data !== null ? (
        <>
          <p className="text-ink-secondary mt-1 text-sm">
            <span className="text-ink font-medium tabular-nums">
              {formatCurrency(data.realised_cents)}
            </span>{" "}
            realised
            {data.missed_periods > 0 ? (
              <>
                {" · "}
                <span className="text-ink font-medium tabular-nums">
                  {data.missed_periods}
                </span>{" "}
                {data.missed_periods === 1 ? "period" : "periods"} went unused
              </>
            ) : null}
          </p>

          {data.redemptions.length === 0 ? (
            <p className="text-ink-muted mt-3 text-sm">
              Nothing recorded yet. Marking a credit used here builds the history.
            </p>
          ) : (
            <ul className="mt-3">
              {data.redemptions.map((entry) => (
                <li
                  key={`${entry.perk_id}-${entry.period_start}`}
                  className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-2 last:border-0"
                >
                  <span className="text-sm">
                    <span className="block font-medium">{entry.perk_name}</span>
                    <span className="text-ink-muted block text-xs">
                      {entry.card_name} · {CADENCE_LABELS[entry.cadence as Cadence]} period from{" "}
                      {formatDate(entry.period_start)}
                      {entry.note ? ` · ${entry.note}` : ""}
                    </span>
                  </span>
                  <span className="text-sm font-medium tabular-nums">
                    {formatCurrency(entry.realised_cents)}
                    {/* A face-value figure is inferred from the credit, not recorded.
                        Saying so keeps "used it all" distinct from "used exactly this". */}
                    {entry.is_face_value ? (
                      <span className="text-ink-muted ml-1 text-[10px] font-normal">full</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </section>
  );
}
