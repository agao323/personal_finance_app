"use client";

/**
 * The cards index: nothing selected yet.
 *
 * On a phone this route *is* the list — the layout renders it full width and this page is
 * hidden. On a wide screen the list sits to the left and this fills the space beside it,
 * so the cross-card view of what is running out has a home without being in the way of the
 * per-card work that is the common case.
 */

import { UpcomingPanel } from "@/components/cards/upcoming";
import { useCards } from "@/components/cards/context";

export default function CardsIndexPage() {
  const { cards, reload, revision } = useCards();

  return (
    <div>
      <UpcomingPanel onChange={reload} revision={revision} />

      <p className="text-ink-secondary mt-4 text-sm">
        {cards && cards.length > 0
          ? "Pick a card to see its credits, fee and history."
          : "Add a credit card account and its credits will live here."}
      </p>
    </div>
  );
}
