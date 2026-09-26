"use client";

/**
 * Delete a card, and everything hanging off it. (Ticket 063)
 *
 * **No ticket numbers and no project state in the copy.** An earlier version told the
 * reader that backups were unfinished. Whether our own backlog is caught up is not
 * something a person deleting a card can act on, and it dates the moment it changes.
 *
 * **The most destructive action in the product.** Every child of `accounts` cascades:
 * ownership stakes, balance snapshots, transactions, import mappings, credits, and every
 * recorded use. Balance snapshots are the one thing here no bank can reproduce.
 *
 * So the dialog does three things a plain "are you sure" does not:
 *   1. names what goes, by count, read from the API rather than guessed — "all data" is a
 *      phrase people click past; "312 balance snapshots going back to March 2024" is not
 *   2. offers **closing** first, which is what most people actually want
 *   3. requires typing the card's name, checked server-side too
 */

import { useEffect, useState } from "react";

import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Card } from "./types";

type Preview = ResponseOf<"/accounts/{account_id}/deletion-preview", "get">;

export function RemoveCard({
  card,
  onDone,
  onCancel,
}: {
  card: Card;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts/{account_id}/deletion-preview", {
      params: { account_id: card.account_id },
    })
      .then((next) => {
        if (live) setPreview(next);
      })
      .catch(() => {
        // Without counts the dialog cannot make an honest case, so it refuses to be a
        // vague one instead.
        if (live) setError("Could not work out what this would delete. Not removing anything.");
      });
    return () => {
      live = false;
    };
  }, [card.account_id]);

  async function close() {
    setBusy(true);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: { closed_at: new Date().toISOString().slice(0, 10) },
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "delete",
        params: { account_id: card.account_id },
        body: { confirm_name: typed },
      });
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not delete.");
    } finally {
      setBusy(false);
    }
  }

  const counts = preview
    ? [
        [preview.balance_snapshots, "balance snapshot"],
        [preview.transactions, "transaction"],
        [preview.ownership_stakes, "ownership record"],
        [preview.card_perks, "credit"],
        [preview.perk_redemptions, "recorded use"],
      ].filter(([n]) => (n as number) > 0)
    : [];

  return (
    <div
      role="alertdialog"
      aria-label={`Remove ${card.name}`}
      className="border-critical/40 bg-surface-1 mt-3 rounded-lg border-2 p-4"
    >
      <h3 className="text-critical-text text-sm font-semibold">Permanently delete {card.name}?</h3>

      {counts.length > 0 ? (
        <>
          <p className="text-ink-secondary mt-2 text-sm">This deletes, and cannot be undone:</p>
          <ul className="text-ink mt-1 list-disc pl-5 text-sm">
            {counts.map(([n, noun]) => (
              <li key={noun as string} className="tabular-nums">
                <strong>{n as number}</strong> {noun as string}
                {(n as number) === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
          {preview?.earliest_snapshot ? (
            <p className="text-ink-secondary mt-1 text-sm">
              Balance history goes back to <strong>{formatDate(preview.earliest_snapshot)}</strong>.
              No bank can reproduce it.
            </p>
          ) : null}
        </>
      ) : preview ? (
        <p className="text-ink-secondary mt-2 text-sm">
          This card has no recorded history yet, so nothing is lost by removing it.
        </p>
      ) : (
        <p className="text-ink-muted mt-2 text-sm">Working out what this would delete…</p>
      )}

      <div className="border-hairline mt-3 rounded-md border p-3">
        <p className="text-sm font-medium">Close it instead?</p>
        <p className="text-ink-secondary mt-1 text-sm">
          Closing stops it counting toward net worth from today and keeps every record. It is almost
          always what you want for a card you have cancelled.
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={() => void close()}
          className="border-hairline hover:bg-surface-2 mt-2 rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
        >
          Close this card
        </button>
      </div>

      <label htmlFor={`confirm-${card.account_id}`} className="mt-4 block text-sm">
        To delete it anyway, type <strong>{card.name}</strong>
      </label>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <input
          id={`confirm-${card.account_id}`}
          type="text"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          className="border-hairline bg-surface-1 rounded-md border px-2 py-1.5 text-sm"
        />
        <button
          type="button"
          disabled={busy || typed.trim() !== card.name}
          onClick={() => void remove()}
          className="bg-critical/10 text-critical-text border-critical/40 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40"
        >
          Delete permanently
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </div>

      {error ? (
        <p role="alert" className="text-critical-text mt-2 text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
