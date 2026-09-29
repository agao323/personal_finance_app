"use client";

/**
 * The monthly review, offered — never generated until it is taken (plan 119).
 *
 * The server offers last month while the advisor is on and no review of it exists; taking it
 * makes the offer go away for good. "Not now" hides it for that month on this device only —
 * a convenience kept in localStorage, which may be missing or blocked, so every read and write
 * is guarded and the offer simply shows again if it cannot remember.
 */

import type { AdvisorStatus } from "@/lib/advisor";
import { formatCurrency } from "@/lib/format";

export type Offer = NonNullable<AdvisorStatus["review_offer"]>;

const DISMISSED_KEY = "pfa:review-offer-dismissed";

/** "2026-08-01" → "August". */
export function monthName(month: string): string {
  return new Date(`${month}T00:00:00Z`).toLocaleString("en-US", {
    month: "long",
    timeZone: "UTC",
  });
}

export function dismissedFor(month: string): boolean {
  try {
    return globalThis.localStorage?.getItem(DISMISSED_KEY) === month;
  } catch {
    return false;
  }
}

function dismiss(month: string): void {
  try {
    globalThis.localStorage?.setItem(DISMISSED_KEY, month);
  } catch {
    // Nowhere to remember it: the offer shows again next visit, which is harmless.
  }
}

export function ReviewOffer({
  offer,
  onAccept,
  onDismiss,
  busy = false,
}: {
  offer: Offer;
  onAccept: () => void;
  onDismiss: () => void;
  busy?: boolean;
}) {
  const name = monthName(offer.month);
  const cost =
    offer.estimated_cost_cents == null
      ? "Free on the local model"
      : `About ${formatCurrency(offer.estimated_cost_cents)}`;

  return (
    <section
      aria-label={`Review ${name}`}
      className="border-hairline bg-surface-1 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4"
    >
      <p className="text-sm">
        <span className="font-medium">Review {name}</span>
        <span className="text-ink-secondary">
          {" "}
          — spending, subscriptions, credits, runway and net worth. {cost}.
        </span>
      </p>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onAccept}
          disabled={busy}
          className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "Starting…" : `Review ${name}`}
        </button>
        <button
          type="button"
          onClick={() => {
            dismiss(offer.month);
            onDismiss();
          }}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Not now
        </button>
      </div>
    </section>
  );
}
