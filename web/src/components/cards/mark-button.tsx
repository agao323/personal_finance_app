"use client";

/**
 * Mark a credit used, or undo it — optionally recording only part of it.
 *
 * Optimistic: the label flips immediately and reverts visibly on failure. This gets
 * pressed on a phone, on a bad connection, and a spinner blocking the row is worse than a
 * state that is wrong for 200ms and corrects itself.
 *
 * `pending` holds the value we are hoping for, so a failure has something to fall back
 * from rather than guessing what the server now thinks.
 */

import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { parseDollarsToCents } from "@/lib/format";
import type { Perk } from "./types";

export function MarkButton({
  perk,
  onChange,
  on,
}: {
  perk: Perk;
  onChange: () => void;
  /** Which period to mark, for backfilling. Omitted means today's. */
  on?: string;
}) {
  const used = perk.current_period?.is_used ?? false;
  const [pending, setPending] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);
  const [partial, setPartial] = useState(false);
  const [amount, setAmount] = useState("");
  const shown = pending ?? used;

  async function toggle(amountCents?: number) {
    const next = amountCents !== undefined ? true : !shown;
    setPending(next);
    setFailed(false);
    setPartial(false);
    try {
      // Two calls rather than a computed method: DELETE takes no body, so a
      // `post | delete` union narrows `body` to undefined and the POST stops
      // type-checking.
      if (next) {
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "post",
          params: { perk_id: perk.id },
          body: {
            ...(on ? { on } : {}),
            ...(amountCents !== undefined ? { amount_cents: amountCents } : {}),
          },
        });
      } else {
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "delete",
          params: { perk_id: perk.id },
          ...(on ? { query: { on } } : {}),
        });
      }
      onChange();
    } catch {
      setPending(null);
      setFailed(true);
    }
  }

  if (partial) {
    return (
      <span className="flex items-center gap-2">
        <label className="text-ink-muted text-xs" htmlFor={`partial-${perk.id}`}>
          Used how much?
        </label>
        <input
          id={`partial-${perk.id}`}
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          className="border-hairline bg-surface-1 w-20 rounded-md border px-2 py-1 text-sm tabular-nums"
        />
        <button
          type="button"
          onClick={() => {
            const cents = parseDollarsToCents(amount);
            if (cents !== null && cents > 0) void toggle(cents);
          }}
          className="bg-accent-bg text-accent-strong rounded-lg px-2.5 py-1 text-sm font-medium"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => setPartial(false)}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2">
      {failed ? (
        <span role="alert" className="text-critical-text text-xs">
          Did not save
        </span>
      ) : null}
      {!shown ? (
        <button
          type="button"
          onClick={() => setPartial(true)}
          className="text-ink-muted hover:text-ink text-xs underline underline-offset-4"
        >
          Part
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => void toggle()}
        aria-pressed={shown}
        className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
          shown ? "bg-accent-bg text-accent-strong" : "border-hairline hover:bg-surface-2 border"
        }`}
      >
        {shown ? "Used" : "Mark used"}
      </button>
    </span>
  );
}
