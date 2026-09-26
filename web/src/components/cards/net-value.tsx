"use client";

/**
 * Is this card paying for itself? (Ticket 059)
 *
 * The decision perk tracking actually serves is not "which credits exist" — it is keep
 * this card or cancel it. Two numbers and their difference.
 *
 * **Deliberately silent on the judgement.** No "you are losing money on this card": a
 * credit you chose not to use is not value destroyed, and the app does not know your
 * reasons. It reports; you decide.
 */

import { formatCurrency, formatDate } from "@/lib/format";
import type { Card } from "./types";

export function NetValue({ card }: { card: Card }) {
  // Absent is not zero. A card with no fee recorded says nothing rather than claiming $0.
  if (card.annual_fee_cents === null || card.annual_fee_cents === undefined) return null;

  const fee = card.annual_fee_cents;
  const realised = card.realised_this_fee_year_cents ?? 0;
  const difference = realised - fee;
  const ahead = difference >= 0;

  return (
    <div className="border-hairline mt-3 rounded-lg border p-3 text-sm">
      <dl className="grid grid-cols-3 gap-3">
        <div>
          <dt className="text-ink-muted text-xs">Annual fee</dt>
          <dd className="mt-0.5 font-medium tabular-nums">{formatCurrency(fee)}</dd>
        </div>
        <div>
          <dt className="text-ink-muted text-xs">Realised this fee year</dt>
          <dd className="mt-0.5 font-medium tabular-nums">{formatCurrency(realised)}</dd>
        </div>
        <div>
          <dt className="text-ink-muted text-xs">Difference</dt>
          <dd
            className={`mt-0.5 font-medium tabular-nums ${
              ahead ? "text-accent-strong" : "text-ink"
            }`}
          >
            {ahead ? "+" : "−"}
            {formatCurrency(Math.abs(difference))}
          </dd>
        </div>
      </dl>
      {card.fee_year_start ? (
        <p className="text-ink-muted mt-2 text-xs">
          Fee year began {formatDate(card.fee_year_start)}. Counts what you recorded using, not what
          was available.
        </p>
      ) : null}
    </div>
  );
}
