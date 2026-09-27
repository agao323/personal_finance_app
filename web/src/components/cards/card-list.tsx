"use client";

/**
 * The master half of master–detail, and where cards are managed. (Tickets 066, 067)
 *
 * Rows are **links, not filters** — each card has a real URL, so the back button works and
 * a card can be bookmarked.
 *
 * Adding, renaming and deleting live here rather than in the detail column. A card is an
 * item in this list; acting on it from the list is where you already are when you decide
 * to, and it means those controls do not disappear the moment you open a card.
 *
 * The row is a `<Link>` with the action buttons as **siblings**, never nested inside it. A
 * button inside an anchor is invalid HTML and behaves unpredictably for keyboard and
 * screen-reader users.
 */

import { useState } from "react";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { IconButton, PencilIcon, TrashIcon, WarningIcon } from "./icons";
import { AddCard } from "./add-card";
import { RemoveCard } from "./remove-card";
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
            onChange={onChange}
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

function CardListRow({
  card,
  selected,
  onChange,
}: {
  card: Card;
  selected: boolean;
  onChange: () => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [name, setName] = useState(card.name);

  // Anything on this card whose current period is short for its own cadence, and unspent.
  const running = card.perks.filter(
    (perk) => perk.is_active && perk.current_period?.is_urgent && !perk.current_period.is_used,
  ).length;

  async function rename() {
    if (!name.trim() || name === card.name) {
      setRenaming(false);
      return;
    }
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: { name },
      });
      onChange();
    } finally {
      setRenaming(false);
    }
  }

  if (renaming) {
    return (
      <li className="border-hairline/60 border-b p-3">
        <label className="sr-only" htmlFor={`rename-${card.account_id}`}>
          Card name
        </label>
        <input
          id={`rename-${card.account_id}`}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="border-hairline bg-surface-1 w-full rounded-md border px-2 py-1 text-sm"
        />
        <span className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => void rename()}
            className="bg-accent-bg text-accent-strong rounded-lg px-2.5 py-1 text-sm font-medium"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setName(card.name);
              setRenaming(false);
            }}
            className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
          >
            Cancel
          </button>
        </span>
      </li>
    );
  }

  return (
    <li
      className={`border-hairline/60 border-b transition-colors ${
        selected ? "bg-accent-bg" : "hover:bg-surface-2"
      }`}
    >
      <div className="flex items-center gap-1 pr-2">
        <Link
          href={`/cards/${card.account_id}`}
          aria-current={selected ? "page" : undefined}
          className="min-w-0 flex-1 px-3 py-2.5"
        >
          <span className="flex items-baseline justify-between gap-2">
            <span
              className={`truncate text-sm font-medium ${selected ? "text-accent-strong" : ""}`}
            >
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

        <span className="flex shrink-0 items-center gap-1">
          <IconButton label={`Rename ${card.name}`} onClick={() => setRenaming(true)}>
            <PencilIcon />
          </IconButton>
          <IconButton
            label={`Delete ${card.name} and all of its history — balances, transactions and credits`}
            tone="critical"
            onClick={() => setRemoving(true)}
          >
            <TrashIcon />
          </IconButton>
        </span>
      </div>

      {removing ? (
        <div className="px-3 pb-3">
          <RemoveCard
            card={card}
            onDone={() => {
              setRemoving(false);
              onChange();
            }}
            onCancel={() => setRemoving(false)}
          />
        </div>
      ) : null}
    </li>
  );
}
