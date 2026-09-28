"use client";

/**
 * Your conversations, newest first. Each person sees only their own.
 *
 * **Delete sits on the conversation it deletes**, and confirms inside that row: the owner
 * looks for a control where its subject is, not in a toolbar. The confirmation says what is
 * true — gone from the app now, and still in any backup file already written.
 */

import Link from "next/link";
import { useState } from "react";

import type { ConversationSummary } from "@/lib/advisor";
import { formatAge } from "@/lib/format";

export function ConversationList({
  conversations,
  onDelete,
}: {
  conversations: ConversationSummary[];
  onDelete: (id: string) => Promise<void>;
}) {
  if (conversations.length === 0) {
    return <p className="text-ink-secondary text-sm">No conversations yet.</p>;
  }
  return (
    <ul aria-label="Conversations" className="divide-hairline divide-y">
      {conversations.map((conversation) => (
        <ConversationRow key={conversation.id} conversation={conversation} onDelete={onDelete} />
      ))}
    </ul>
  );
}

function ConversationRow({
  conversation,
  onDelete,
}: {
  conversation: ConversationSummary;
  onDelete: (id: string) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastUsed = (conversation.last_turn_at ?? conversation.created_at).slice(0, 10);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await onDelete(conversation.id);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not delete.");
      setBusy(false);
    }
  }

  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <Link href={`/advisor/${conversation.id}`} className="min-w-0 flex-1">
          <span className="text-ink block truncate text-sm font-medium">{conversation.title}</span>
          <span className="text-ink-muted text-xs">
            {conversation.view === "mine" ? "Mine" : "Household"} · {conversation.turn_count}{" "}
            {conversation.turn_count === 1 ? "question" : "questions"} · {formatAge(lastUsed)}
          </span>
        </Link>
        {confirming ? null : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            aria-label={`Delete “${conversation.title}”`}
            className="text-ink-secondary hover:text-critical-text shrink-0 text-xs underline underline-offset-4"
          >
            Delete
          </button>
        )}
      </div>
      {confirming ? (
        <div role="alertdialog" aria-label="Delete this conversation" className="mt-2 text-sm">
          <p className="text-ink">
            Delete this conversation? It is gone from the app now. Copies in backup files already
            written remain.
          </p>
          <div className="mt-2 flex gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => void remove()}
              className="bg-critical/10 text-critical-text border-critical/40 rounded-lg border px-3 py-1 text-sm font-medium disabled:opacity-40"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
            >
              Keep it
            </button>
          </div>
          {error ? (
            <p role="alert" className="text-critical-text mt-2">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
