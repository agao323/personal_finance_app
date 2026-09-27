"use client";

/**
 * One card. (Ticket 066)
 *
 * The card itself comes from the list the layout already loaded, so navigating between
 * cards does not refetch the wallet — it is the same data, already in hand.
 */

import { use } from "react";

import { CardDetail } from "@/components/cards/card-detail";
import { useCards } from "@/components/cards/context";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";

export default function CardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { cards, pending, error, reload, revision } = useCards();

  // `pending` is the first load only (ticket 070), so marking a credit no longer replaces
  // the whole card with a skeleton — the figures update where they are.
  if (pending) return <Skeleton className="h-64 w-full" />;

  // Without the wallet there is no way to know whether this card exists, and "No such
  // card" would be a guess dressed as a fact.
  if (cards === null) return <ErrorState detail={error ?? undefined} onRetry={reload} />;

  const card = cards.find((candidate) => candidate.account_id === Number(id));

  if (!card) {
    // Says so rather than rendering an empty shell that looks like a card with no credits.
    return (
      <EmptyState
        title="No such card"
        detail="It may have been removed, or the link may be out of date."
      />
    );
  }

  return <CardDetail card={card} revision={revision} onChange={reload} />;
}
