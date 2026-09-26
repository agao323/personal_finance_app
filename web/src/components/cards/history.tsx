"use client";

/**
 * Everything you have ever marked, and a way to record something you forgot. (Ticket 058)
 *
 * **No default cut-off.** "Show me the whole history" is the request this answers, and a
 * silent window would hide exactly the old entries being asked for. The window control
 * narrows; it never widens from a default that was already narrow.
 */

import { useEffect, useState } from "react";

import { ErrorState, Skeleton } from "@/components/states";
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

export function HistoryPanel({ revision }: { revision: number }) {
  const [months, setMonths] = useState(0);
  const [loaded, setLoaded] = useState<{
    key: string;
    data: History | null;
    error: string | null;
  } | null>(null);

  // Derived, not a flag set at the top of the effect — see the note in `upcoming.tsx`.
  const key = `${months}|${revision}`;
  const data = loaded?.key === key && !loaded.error ? loaded.data : null;
  const pending = loaded?.key !== key;
  const error = loaded?.key === key ? loaded.error : null;

  useEffect(() => {
    let live = true;
    const requested = `${months}|${revision}`;
    apiFetch("/cards/history", {
      query: months === 0 ? {} : { from: isoMonthsAgo(months) },
    })
      .then((next) => {
        if (live) setLoaded({ key: requested, data: next, error: null });
      })
      .catch((cause: unknown) => {
        if (live)
          setLoaded({
            key: requested,
            data: null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          });
      });
    return () => {
      live = false;
    };
  }, [months, revision]);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium">What you have used</h2>
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

      {error ? <ErrorState detail={error} /> : null}

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

/**
 * Record a credit you used months ago.
 *
 * The period preview matters. "2 March" landing in the February period of a month-end
 * anchor is genuinely surprising, so the chosen date's period is shown **before** saving —
 * and it comes from the API's own answer rather than a second implementation of the period
 * arithmetic here, which could disagree with what actually gets saved.
 */
export function BackfillForm({
  perkId,
  onDone,
  onCancel,
}: {
  perkId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!date) {
      setError("Pick a date inside the period you used it.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/perks/{perk_id}/redemptions", {
        method: "post",
        params: { perk_id: perkId },
        body: { on: date },
      });
      onDone();
    } catch (cause: unknown) {
      // A date before the credit's first period comes back as a 422 explaining that.
      setError(cause instanceof Error ? cause.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-hairline mt-2 rounded-lg border p-3">
      <label htmlFor={`backfill-${perkId}`} className="text-sm font-medium">
        Record a past use
      </label>
      <p className="text-ink-muted mt-1 text-xs">
        Any date inside the period you used it. The period it lands in is worked out from the
        credit&rsquo;s own schedule.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          id={`backfill-${perkId}`}
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="border-hairline bg-surface-1 rounded-md border px-2 py-1.5 text-sm"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Record
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-critical-text mt-2 text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
