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
import { centsToInputValue, formatCurrency, formatDate, parseDollarsToCents } from "@/lib/format";
import {
  PERIODS_BACK,
  PERIOD_NOUN,
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
  const [partialOpen, setPartialOpen] = useState(false);

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
        <p className="text-sm font-medium">
          Which {PERIOD_NOUN[cadence].many} did you use this in?
        </p>
        {refreshing ? <Refreshing /> : null}
      </div>
      <p className="text-ink-muted mt-1 text-xs">
        One tap records the full {formatCurrency(perk.value_cents)} for that{" "}
        {PERIOD_NOUN[cadence].one}. Tap again to undo it.
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

          {/* One row, so the two links do not run into each other. */}
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {!partialOpen ? (
              <button
                type="button"
                onClick={() => setPartialOpen(true)}
                className="text-ink-secondary hover:text-ink text-xs underline underline-offset-4"
              >
                Used only part of one?
              </button>
            ) : null}
            {data.has_earlier ? (
              <button
                type="button"
                onClick={() => setPages((current) => current + 1)}
                disabled={back >= MOST_PERIODS}
                className="text-ink-secondary hover:text-ink text-xs underline underline-offset-4 disabled:opacity-50"
              >
                Show earlier
              </button>
            ) : null}
          </div>

          {partialOpen ? (
            <PartialForm
              perkId={perk.id}
              cadence={cadence}
              periods={data.periods}
              onClose={() => setPartialOpen(false)}
              onDone={onChange}
            />
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

  // **Always rendered, so every chip is the same height.** Conditionally, a row holding the
  // current period or a partial amount grew taller than the rows around it and the grid
  // stepped. A non-breaking space keeps the line box when there is nothing to say.
  //
  // A current period that also carries an amount shows the amount: it is the rarer and more
  // informative fact, and "now" is already carried by the ring, the last position, and the
  // accessible name.
  const second =
    used && period.used_amount_cents != null
      ? formatCurrency(period.used_amount_cents)
      : period.is_current
        ? "now"
        : "\u00a0";

  return (
    <button
      type="button"
      aria-pressed={used}
      aria-label={`${label}, ${state}${period.is_current ? ", current period" : ""}. The ${range}.`}
      onClick={onToggle}
      className={`rounded-md border px-2 py-1.5 text-center text-xs transition-colors ${
        used
          ? "bg-accent-bg text-accent-strong border-transparent font-medium"
          : "border-hairline text-ink-secondary hover:bg-surface-2"
      } ${period.is_current ? "ring-accent/50 ring-1" : ""} ${
        failed ? "border-critical-text" : ""
      }`}
    >
      <span className="block truncate tabular-nums">{label}</span>
      {/* A partial redemption is a different fact from "used it all" and the grid must not
          flatten the two into one filled chip. */}
      <span
        aria-hidden={second === "\u00a0"}
        className={`block truncate text-[10px] font-normal ${
          used && period.used_amount_cents != null ? "" : "text-ink-muted"
        }`}
      >
        {second}
      </span>
    </button>
  );
}

/**
 * Record part of a period's value, for any period. (Ticket 077)
 *
 * `MarkButton` has had a "Part" control since 053, but only ever for the period you are in,
 * so a credit you half-used in March could be recorded as all or nothing and no more.
 *
 * A separate control rather than a second gesture on the chip: tapping a used chip un-marks
 * it, which is the common correction, and hiding an amount editor behind that tap would make
 * undo a two-step operation in order to serve the rarer case. One tap still records the full
 * value; the fast path does not get slower to make room for this.
 */
function PartialForm({
  perkId,
  cadence,
  periods,
  onClose,
  onDone,
}: {
  perkId: number;
  cadence: Cadence;
  periods: PeriodState[];
  onClose: () => void;
  onDone: () => void;
}) {
  // Newest first here, unlike the grid: the period you are correcting is usually a recent
  // one, and a select is read from the top.
  const choices = [...periods].reverse();
  const [start, setStart] = useState(choices[0]?.start ?? "");
  const chosen = choices.find((period) => period.start === start);
  // Prefilled from whatever that period already has, so this reads as a correction rather
  // than a blank form.
  const [amount, setAmount] = useState(
    choices[0]?.used_amount_cents != null ? centsToInputValue(choices[0].used_amount_cents) : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const cents = parseDollarsToCents(amount);
    if (cents === null || cents <= 0) {
      // Zero is not a partial use, it is an unused period, and the chip already says that.
      setError("Enter how much of it you used.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // The same endpoint one tap uses. It updates the amount when a period is already
      // marked, so this corrects a full mark as readily as it records a new partial one.
      await apiFetch("/perks/{perk_id}/redemptions", {
        method: "post",
        params: { perk_id: perkId },
        body: { on: start, amount_cents: cents },
      });
      onClose();
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-hairline/60 mt-2 border-t pt-2">
      <div className="flex flex-wrap items-end gap-2">
        <span className="flex flex-col gap-1">
          <label htmlFor={`partial-period-${perkId}`} className="text-ink-muted text-[11px]">
            Which {PERIOD_NOUN[cadence].one}
          </label>
          <select
            id={`partial-period-${perkId}`}
            value={start}
            onChange={(event) => {
              setStart(event.target.value);
              const next = choices.find((period) => period.start === event.target.value);
              setAmount(
                next?.used_amount_cents != null ? centsToInputValue(next.used_amount_cents) : "",
              );
            }}
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1 text-sm"
          >
            {choices.map((period) => (
              <option key={period.start} value={period.start}>
                {periodLabel(cadence, period.start)}
              </option>
            ))}
          </select>
        </span>
        <span className="flex flex-col gap-1">
          <label htmlFor={`partial-amount-${perkId}`} className="text-ink-muted text-[11px]">
            Amount used
          </label>
          <input
            id={`partial-amount-${perkId}`}
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="border-hairline bg-surface-1 w-24 rounded-md border px-2 py-1 text-sm tabular-nums"
          />
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="bg-accent-bg text-accent-strong rounded-lg px-2.5 py-1 text-sm font-medium disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </div>
      {chosen && !chosen.is_used ? (
        <p className="text-ink-muted mt-1 text-[11px]">
          That {PERIOD_NOUN[cadence].one} is not marked yet. Saving marks it for this amount.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-critical-text mt-1 text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
