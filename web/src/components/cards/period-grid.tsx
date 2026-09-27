"use client";

/**
 * Which periods you used this credit in. (Ticket 069)
 *
 * **A credit is used or not used, per period.** That is what the data has always recorded —
 * a redemption is `(perk_id, period_start)` and its presence is the whole state; nothing
 * anywhere stores the day you spent it. The old form asked for a date anyway and then spent
 * two paragraphs explaining which period that date would land in, which is the period
 * arithmetic leaking into the interface. Here you tap the month.
 *
 * The periods come from the API, never from arithmetic done here. Reimplementing
 * `add_months` and its day-of-month clamping in TypeScript is exactly the second
 * implementation `services/perks.py` exists to prevent, and it would disagree about a perk
 * anchored on the 31st — a chip labelled February marking the period that ends in March.
 */

import { useEffect, useState } from "react";

import { ErrorState, Refreshing, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import {
  PERIODS_BACK,
  periodLabel,
  type Cadence,
  type Perk,
  type PeriodState,
  type Periods,
} from "./types";

/** The API's own ceiling on `back`. Asking for more is an error, not more history. */
const MOST_PERIODS = 60;

interface Loaded {
  key: string;
  data: Periods | null;
  error: string | null;
}

export function PeriodGrid({
  perk,
  revision,
  onChange,
}: {
  perk: Perk;
  /** The screen's refresh counter, so marking from anywhere else shows up here too. */
  revision: number;
  onChange: () => void;
}) {
  const cadence = perk.cadence as Cadence;
  const [pages, setPages] = useState(1);
  const back = Math.min(MOST_PERIODS, PERIODS_BACK[cadence] * pages);

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  /**
   * Chips whose new state we are hoping for.
   *
   * Optimistic for the same reason the mark button is: this gets tapped several times in a
   * row when filling in a year you forgot, and a round trip per tap with the chip inert in
   * between makes the grid feel broken.
   */
  const [guesses, setGuesses] = useState<Record<string, boolean>>({});
  const [failed, setFailed] = useState<string | null>(null);

  const key = `${back}|${revision}`;
  const data = loaded?.data ?? null;
  const pending = loaded === null;
  const refreshing = loaded !== null && loaded.key !== key;
  const error = loaded?.error ?? null;

  useEffect(() => {
    let live = true;
    const requested = `${back}|${revision}`;
    apiFetch("/perks/{perk_id}/periods", {
      params: { perk_id: perk.id },
      query: { back },
    })
      .then((next) => {
        if (!live) return;
        setLoaded({ key: requested, data: next, error: null });
        // Drop the guesses this response has caught up with, and **only** those. Clearing
        // all of them would flicker a chip tapped while this request was already in flight.
        setGuesses((current) => {
          const outstanding: Record<string, boolean> = {};
          for (const [start, guess] of Object.entries(current)) {
            const row = next.periods.find((period) => period.start === start);
            if (row && row.is_used !== guess) outstanding[start] = guess;
          }
          return outstanding;
        });
      })
      .catch((cause: unknown) => {
        if (live)
          setLoaded((previous) => ({
            key: requested,
            data: previous?.data ?? null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          }));
      });
    return () => {
      live = false;
    };
  }, [perk.id, back, revision]);

  async function toggle(start: string, used: boolean) {
    setGuesses((current) => ({ ...current, [start]: !used }));
    setFailed(null);
    try {
      if (used) {
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "delete",
          params: { perk_id: perk.id },
          query: { on: start },
        });
      } else {
        // The period's own start date. It is a date inside the period by definition, so it
        // resolves to that period and nothing here has to know how.
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "post",
          params: { perk_id: perk.id },
          body: { on: start },
        });
      }
      onChange();
    } catch {
      setGuesses((current) => {
        const next = { ...current };
        delete next[start];
        return next;
      });
      setFailed(start);
    }
  }

  return (
    <div className="border-hairline mt-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium">Which periods did you use this in?</p>
        {refreshing ? <Refreshing /> : null}
      </div>
      <p className="text-ink-muted mt-1 text-xs">
        One tap records the full {formatCurrency(perk.value_cents)} for that period. Tap again to
        undo it.
      </p>

      {error && data === null ? <ErrorState detail={error} /> : null}
      {pending && !error ? <Skeleton className="mt-3 h-16 w-full" /> : null}

      {data !== null && data.periods.length === 0 ? (
        <p className="text-ink-muted mt-2 text-xs">
          This credit&rsquo;s first period has not begun yet, so there is nothing to record.
        </p>
      ) : null}

      {data !== null && data.periods.length > 0 ? (
        <>
          <div className="mt-2 grid grid-cols-3 gap-1.5 sm:grid-cols-4">
            {data.periods.map((period) => (
              <PeriodChip
                key={period.start}
                cadence={cadence}
                period={period}
                used={guesses[period.start] ?? period.is_used}
                failed={failed === period.start}
                onToggle={() => void toggle(period.start, guesses[period.start] ?? period.is_used)}
              />
            ))}
          </div>

          {data.has_earlier ? (
            <button
              type="button"
              onClick={() => setPages((current) => current + 1)}
              disabled={back >= MOST_PERIODS}
              className="text-ink-secondary hover:text-ink mt-2 text-xs underline underline-offset-4 disabled:opacity-50"
            >
              Show earlier
            </button>
          ) : null}
        </>
      ) : null}

      {failed !== null ? (
        <p role="alert" className="text-critical-text mt-2 text-xs">
          That did not save. Nothing was changed.
        </p>
      ) : null}
    </div>
  );
}

/**
 * One period, as a toggle.
 *
 * The label names the calendar unit; the accessible name carries the exact half-open range,
 * because a perk anchored mid-month has periods that a short label can only approximate.
 */
function PeriodChip({
  cadence,
  period,
  used,
  failed,
  onToggle,
}: {
  cadence: Cadence;
  period: PeriodState;
  used: boolean;
  failed: boolean;
  onToggle: () => void;
}) {
  const label = periodLabel(cadence, period.start);
  const state = used ? "used" : "not used";
  const range = `period from ${formatDate(period.start)}, resets ${formatDate(period.end)}`;

  return (
    <button
      type="button"
      aria-pressed={used}
      aria-label={`${label}, ${state}. The ${range}.`}
      onClick={onToggle}
      className={`rounded-md border px-2 py-1.5 text-center text-xs transition-colors ${
        used
          ? "bg-accent-bg text-accent-strong border-transparent font-medium"
          : "border-hairline text-ink-secondary hover:bg-surface-2"
      } ${period.is_current ? "ring-accent/50 ring-1" : ""} ${
        failed ? "border-critical-text" : ""
      }`}
    >
      <span className="block tabular-nums">{label}</span>
      {/* A partial redemption is a different fact from "used it all" and the grid must not
          flatten the two into one filled chip. */}
      {used && period.used_amount_cents != null ? (
        <span className="block text-[10px] font-normal">
          {formatCurrency(period.used_amount_cents)}
        </span>
      ) : null}
      {period.is_current ? (
        <span className="text-ink-muted block text-[10px] font-normal">now</span>
      ) : null}
    </button>
  );
}
