"use client";

/**
 * The advisor: somewhere to ask, your conversations, and whether it is on.
 *
 * Starting a conversation asks in the dashboard's Mine / Household view — the same toggle,
 * the same stored preference — because that is how the owner is already reading their
 * numbers. The first question travels to the conversation screen in sessionStorage, never
 * the URL (see `lib/advisor.ts`).
 *
 * **Settled lists stay on screen.** Deleting a conversation removes that row and nothing
 * else; nothing here ever collapses to a skeleton once it has loaded.
 */

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConversationList } from "@/components/advisor/conversation-list";
import { QuestionBox } from "@/components/advisor/question-box";
import { StatusLine } from "@/components/advisor/status-line";
import { ErrorState, Skeleton } from "@/components/states";
import { ViewToggle, useViewScope } from "@/components/view-toggle";
import { stashQuestion, type AdvisorStatus, type ConversationSummary } from "@/lib/advisor";
import { apiFetch } from "@/lib/api";

export default function AdvisorPage() {
  return <AdvisorScreen />;
}

export function AdvisorScreen() {
  const router = useRouter();
  const [view, setView] = useViewScope();
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([apiFetch("/advisor/status"), apiFetch("/advisor/conversations")])
      .then(([nextStatus, list]) => {
        if (!live) return;
        setStatus(nextStatus);
        setConversations(list);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, []);

  async function ask(question: string) {
    setAsking(true);
    setError(null);
    try {
      const created = await apiFetch("/advisor/conversations", {
        method: "post",
        body: { view },
      });
      stashQuestion(created.id, question);
      router.push(`/advisor/${created.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not start a conversation.");
      setAsking(false);
    }
  }

  async function remove(id: string) {
    await apiFetch("/advisor/conversations/{conversation_id}", {
      method: "delete",
      params: { conversation_id: id },
    });
    setConversations((list) => (list ?? []).filter((c) => c.id !== id));
  }

  if (status === null || conversations === null) {
    if (error) return <ErrorState title="The advisor is unavailable" detail={error} />;
    return <Skeleton className="h-64 w-full" />;
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold">Advisor</h1>
        <StatusLine status={status} />
      </header>

      <section aria-label="Ask" className="border-hairline bg-surface-1 rounded-xl border p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-ink-secondary text-sm">Ask in</span>
          <ViewToggle view={view} onChange={setView} />
        </div>
        <QuestionBox onAsk={ask} disabled={!status.enabled} busy={asking} />
        {error ? (
          <p role="alert" className="text-critical-text mt-2 text-sm">
            {error}
          </p>
        ) : null}
      </section>

      <section aria-label="Your conversations">
        <h2 className="text-ink-secondary mb-1 text-sm">Your conversations</h2>
        <ConversationList conversations={conversations} onDelete={remove} />
      </section>
    </div>
  );
}
