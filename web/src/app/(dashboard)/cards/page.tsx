"use client";

/**
 * Credit cards and the credits on them.
 *
 * **Aggregate first, card second.** Both MaxRewards and Kudos lead with every credit you
 * can still use across the whole wallet and treat a single card as the drill-down. The
 * first version of this page did the reverse — a fixed 45-day band, then a card list —
 * which answered "what does card three hold" rather than "what can I use".
 *
 * Composition only. Each panel owns its own file so the pieces could be built in parallel:
 * `upcoming.tsx` (056), `card-row.tsx` (055), `perk-form.tsx` (057), `history.tsx` (058),
 * `net-value.tsx` (059).
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { CardRow } from "@/components/cards/card-row";
import { HistoryPanel } from "@/components/cards/history";
import { UpcomingPanel } from "@/components/cards/upcoming";
import type { Cards } from "@/components/cards/types";
import { apiFetch } from "@/lib/api";

export default function CardsPage() {
  const [loaded, setLoaded] = useState<{
    key: number;
    cards: Cards | null;
    error: string | null;
  } | null>(null);
  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => setRevision((n) => n + 1), []);

  // Derived from a cell only ever written by a settled response, rather than a flag set
  // at the top of the effect — which would be a synchronous setState inside an effect.
  const cards = loaded?.key === revision && !loaded.error ? loaded.cards : null;
  const pending = loaded?.key !== revision;
  const error = loaded?.key === revision ? loaded.error : null;

  useEffect(() => {
    let live = true;
    const requested = revision;
    apiFetch("/cards")
      .then((next) => {
        if (live) setLoaded({ key: requested, cards: next, error: null });
      })
      .catch((cause: unknown) => {
        if (live)
          setLoaded({
            key: requested,
            cards: null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          });
      });
    return () => {
      live = false;
    };
  }, [revision]);

  return (
    <div>
      <h1 className="text-xl font-medium tracking-tight">Cards</h1>

      {error ? <ErrorState detail={error} onRetry={reload} /> : null}

      <div className="mt-4">
        <UpcomingPanel onChange={reload} />
      </div>

      {pending && !error ? (
        <Skeleton className="mt-4 h-40 w-full" />
      ) : cards !== null && cards.length === 0 ? (
        <div className="mt-4">
          {/* An empty state that carries the next action, not a dead end. Cards are
              accounts, so adding one happens there — a second way to create an account
              would be a second source of truth for the same row. */}
          <EmptyState
            title="No credit cards yet"
            detail="A card is an account with the credit card subtype. Add one, then its credits live here."
            action={
              <Link
                href="/accounts/new"
                className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 text-sm transition-colors"
              >
                Add a card
              </Link>
            }
          />
        </div>
      ) : (
        (cards ?? []).map((card) => <CardRow key={card.account_id} card={card} onChange={reload} />)
      )}

      {cards !== null && cards.length > 0 ? (
        <>
          <HistoryPanel revision={revision} />
          <p className="text-ink-muted mt-4 text-xs">
            Cards are accounts.{" "}
            <Link href="/accounts/new" className="text-accent underline underline-offset-4">
              Add another card
            </Link>
            .
          </p>
        </>
      ) : null}
    </div>
  );
}
