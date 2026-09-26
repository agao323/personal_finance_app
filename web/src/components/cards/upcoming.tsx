"use client";

/**
 * What is about to be lost. (Ticket 056)
 *
 * Replaces a fixed 45-day band, which was unhelpful in both directions: 45 days is noise
 * on a monthly credit — urgent for most of its life — and it hid annual credits entirely.
 *
 * **Urgency is never recomputed here.** `services/perks.is_urgent` decides it, per
 * cadence, and this reads the flag. A second implementation in the browser would drift,
 * and the symptom would be a page calling a credit safe while the API called it urgent.
 */

import { useCallback, useEffect, useState } from "react";

import { ErrorState, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { MarkButton } from "./mark-button";
import { CADENCE_LABELS, expiryLabel, type Cadence, type Upcoming } from "./types";

const HORIZONS = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 180, label: "6 months" },
  { days: 366, label: "Everything" },
] as const;

const STORAGE_KEY = "pfa:cards:horizon";
const DEFAULT_HORIZON = 90;

/**
 * The horizon last chosen, or the default.
 *
 * `localStorage` throws outright in some contexts (a private window, thumbnail capture,
 * site data blocked), so every read is guarded and an unreadable store simply means the
 * default.
 */
function storedHorizon(): number {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    const parsed = raw === null || raw === undefined ? Number.NaN : Number.parseInt(raw, 10);
    return HORIZONS.some((h) => h.days === parsed) ? parsed : DEFAULT_HORIZON;
  } catch {
    return DEFAULT_HORIZON;
  }
}

/** One cell holding the request it answers. See the note below. */
interface Loaded {
  key: string;
  data: Upcoming | null;
  error: string | null;
}

export function UpcomingPanel({
  onChange,
  revision,
}: {
  onChange: () => void;
  /**
   * The screen's refresh counter. Ticket 061: this panel used to fetch on a counter only
   * its own button bumped, so marking a credit from a card row left the total and the list
   * stale until a reload. One signal for the screen — "which panels does this affect" is
   * not a question every caller should have to answer correctly.
   */
  revision: number;
}) {
  // Lazily, from the store. Reading it in an effect and calling setState would be a
  // synchronous setState inside an effect — a cascading render, and what the
  // `react-hooks` rule forbids. `storedHorizon` returns the default whenever the store
  // is unreadable, which includes a server render.
  const [horizon, setHorizon] = useState<number>(storedHorizon);
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  // Derived from state only ever written by a settled response, rather than a `loading`
  // flag set at the top of the effect. Same pattern as the net worth chart.
  const key = `${horizon}|${revision}`;
  const data = loaded?.key === key && !loaded.error ? loaded.data : null;
  const pending = loaded?.key !== key;
  const error = loaded?.key === key ? loaded.error : null;

  const choose = useCallback((days: number) => {
    setHorizon(days);
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, String(days));
    } catch {
      // A horizon that does not persist is a small loss; a crash is not.
    }
  }, []);

  useEffect(() => {
    let live = true;
    const requested = `${horizon}|${revision}`;
    apiFetch("/perks/upcoming", { query: { within_days: horizon } })
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
  }, [horizon, revision]);

  // Marking from here bumps the same counter everything else reads, so the card rows
  // and the history below update too.
  const reload = onChange;

  const urgent = (data?.perks ?? []).filter((row) => row.perk.current_period?.is_urgent);
  const rest = (data?.perks ?? []).filter((row) => !row.perk.current_period?.is_urgent);

  return (
    <section className="border-hairline bg-surface-1 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium">Available to use</h2>
        <div role="group" aria-label="How far ahead" className="flex flex-wrap gap-1">
          {HORIZONS.map((option) => (
            <button
              key={option.days}
              type="button"
              aria-pressed={horizon === option.days}
              onClick={() => choose(option.days)}
              className={`rounded-md px-2 py-1 text-xs transition-colors ${
                horizon === option.days
                  ? "bg-accent-bg text-accent-strong font-medium"
                  : "text-ink-secondary hover:text-ink"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error ? <ErrorState detail={error} onRetry={reload} /> : null}

      {pending && !error ? (
        <Skeleton className="mt-3 h-20 w-full" />
      ) : data !== null && data.perks.length === 0 ? (
        <p className="text-ink-secondary mt-3 text-sm">
          Nothing left to use in this window. Everything available has been marked.
        </p>
      ) : data !== null ? (
        <>
          <p className="text-ink-secondary mt-1 text-sm">
            <span className="text-ink font-medium tabular-nums">
              {formatCurrency(data.total_cents)}
            </span>{" "}
            available
            {data.urgent_cents > 0 ? (
              <>
                {" · "}
                <span className="text-warning-text font-medium tabular-nums">
                  {formatCurrency(data.urgent_cents)}
                </span>{" "}
                running out
              </>
            ) : null}
          </p>

          {urgent.length > 0 ? (
            <Group title="Running out" rows={urgent} onChange={reload} urgent />
          ) : null}
          {rest.length > 0 ? <Group title="Plenty of time" rows={rest} onChange={reload} /> : null}
        </>
      ) : null}
    </section>
  );
}

function Group({
  title,
  rows,
  onChange,
  urgent = false,
}: {
  title: string;
  rows: Upcoming["perks"];
  onChange: () => void;
  urgent?: boolean;
}) {
  return (
    <div className="mt-3">
      <h3 className="text-ink-muted text-[11px] font-medium tracking-wide uppercase">{title}</h3>
      <ul className="mt-1">
        {rows.map((row) => {
          const period = row.perk.current_period;
          return (
            <li
              key={row.perk.id}
              className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-2 last:border-0"
            >
              <span className="text-sm">
                <span className="block font-medium">{row.perk.name}</span>
                <span className="text-ink-muted block text-xs">
                  {row.card_name} · {formatCurrency(row.perk.value_cents)} ·{" "}
                  {CADENCE_LABELS[row.perk.cadence as Cadence]}
                </span>
              </span>
              <span className="flex items-center gap-3 text-sm">
                {/* Never colour alone — the icon and the word carry it too. */}
                <span
                  className={`flex items-center gap-1 text-xs font-medium ${
                    urgent ? "text-warning-text" : "text-ink-muted"
                  }`}
                >
                  {urgent ? <span aria-hidden="true">⚠</span> : null}
                  {period ? expiryLabel(period.days_remaining) : "—"}
                </span>
                <MarkButton perk={row.perk} onChange={onChange} />
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
