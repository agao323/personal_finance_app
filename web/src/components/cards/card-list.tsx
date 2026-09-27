"use client";

/**
 * The master half of master–detail. (Tickets 066, 067, 072)
 *
 * Rows are **links, not filters** — each card has a real URL, so the back button works and
 * a card can be bookmarked.
 *
 * **A list of cards, and nothing else.** Renaming and deleting live in the card's own panel
 * (ticket 072). 066 put them here so they would not disappear when a card was open, which
 * was the wrong trade: with a card open its panel is where you are looking, and two icon
 * buttons per row crowded out the name and the figure the row exists to show.
 *
 * Adding stays, because it acts on the list rather than on any one card.
 */

import { useState } from "react";
import Link from "next/link";

import { formatCurrency } from "@/lib/format";
import { WarningIcon } from "./icons";
import { AddCard } from "./add-card";
import type { Card, Cards } from "./types";

export function CardList({
  cards,
  selectedId,
  onChange,
}: {
  cards: Cards;
  selectedId?: number;
  onChange: () => void;
}) {
  const [adding, setAdding] = useState(false);

  return (
    <div>
      <ul>
        {/* The way back to the cross-card view. Without it the only route out of a card
            was editing the URL. */}
        <li>
          <Link
            href="/cards"
            aria-current={selectedId === undefined ? "page" : undefined}
            className={`border-hairline/60 block border-b px-3 py-2.5 text-sm transition-colors ${
              selectedId === undefined
                ? "bg-accent-bg text-accent-strong font-medium"
                : "text-ink-secondary hover:bg-surface-2 hover:text-ink"
            }`}
          >
            Overview
          </Link>
        </li>

        {cards.map((card) => (
          <CardListRow
            key={card.account_id}
            card={card}
            selected={card.account_id === selectedId}
          />
        ))}
      </ul>

      <div className="border-hairline/60 border-t">
        {adding ? (
          <AddCard
            onDone={() => {
              setAdding(false);
              onChange();
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <div className="p-3">
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="border-hairline hover:bg-surface-2 block w-full rounded-lg border px-3 py-1.5 text-center text-sm transition-colors"
            >
              Add a card
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CardListRow({ card, selected }: { card: Card; selected: boolean }) {
  // Anything on this card whose current period is short for its own cadence, and unspent.
  const running = card.perks.filter(
    (perk) => perk.is_active && perk.current_period?.is_urgent && !perk.current_period.is_used,
  ).length;

  return (
    <li
      className={`border-hairline/60 border-b transition-colors ${
        selected ? "bg-accent-bg" : "hover:bg-surface-2"
      }`}
    >
      <Link
        href={`/cards/${card.account_id}`}
        aria-current={selected ? "page" : undefined}
        className="block px-3 py-2.5"
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className={`truncate text-sm font-medium ${selected ? "text-accent-strong" : ""}`}>
            {card.name}
          </span>
          {running > 0 ? (
            <span
              title={`${running} running out`}
              className="text-warning-text flex shrink-0 items-center gap-0.5 text-xs font-medium"
            >
              <WarningIcon />
              {running}
            </span>
          ) : null}
        </span>
        <span className="text-ink-muted mt-0.5 flex items-baseline justify-between gap-2 text-xs">
          <span className="truncate">{card.institution ?? "—"}</span>
          <span className="shrink-0 tabular-nums">{formatCurrency(card.unused_cents)}</span>
        </span>
        {card.is_closed ? (
          <span className="text-ink-muted mt-0.5 block text-[10px] tracking-wide uppercase">
            closed
          </span>
        ) : null}
      </Link>
    </li>
  );
}
