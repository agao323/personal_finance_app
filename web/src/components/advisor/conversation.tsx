"use client";

/**
 * A conversation: its turns, the one being written, and the box for the next question.
 *
 * - **The first question** comes from the list screen through sessionStorage (`takeQuestion`)
 *   and is sent once. Starting it a tick after mount keeps React's development double-mount
 *   from sending it twice or cancelling it.
 * - **Streaming touches only the newest turn.** Each event replaces that one turn object;
 *   the others keep their identity, and `TurnCard` is memoised, so they do not re-render.
 * - **Stop and leaving both abort.** The abort travels through the proxy to the API, which
 *   cancels the turn and stops the model — and the spending.
 * - **Feedback updates one turn in place**; the conversation is never reloaded for it.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { TurnCard, type TurnView } from "@/components/advisor/answer";
import { QuestionBox } from "@/components/advisor/question-box";
import { StatusLine } from "@/components/advisor/status-line";
import { ErrorState, Skeleton } from "@/components/states";
import { takeQuestion, type AdvisorStatus } from "@/lib/advisor";
import { streamTurn, type AdvisorEvent } from "@/lib/advisor-stream";
import { ApiError, apiFetch, type ResponseOf } from "@/lib/api";

type Detail = ResponseOf<"/advisor/conversations/{conversation_id}", "get">;
type StoredTurn = Detail["turns"][number];

function fromStored(turn: StoredTurn): TurnView {
  return {
    key: turn.id,
    id: turn.id,
    question: turn.question,
    status: turn.status,
    phase: "done",
    text: turn.answer?.text ?? "",
    answer: turn.answer ?? null,
    lookups: turn.lookups,
    error: turn.error ? { code: turn.error, resetsOn: null } : null,
    feedback: turn.feedback ?? null,
    feedbackNote: turn.feedback_note ?? null,
  };
}

/** One event applied to the turn being written. */
export function applyEvent(turn: TurnView, event: AdvisorEvent): TurnView {
  switch (event.type) {
    case "turn_started":
      return { ...turn, id: event.turn_id };
    case "tool_call":
      return { ...turn, lookups: [...turn.lookups, event.lookup] };
    case "text_delta":
      return { ...turn, text: turn.text + event.text, phase: "checking" };
    case "regenerating":
      return { ...turn, text: "", phase: "regenerating" };
    case "answer":
      return { ...turn, answer: event.answer, text: event.answer.text, phase: "done" };
    case "error":
      return {
        ...turn,
        phase: "done",
        status: event.code === "refusal" ? "refused" : "failed",
        error: { code: event.code, resetsOn: event.resets_on ?? null },
      };
    case "turn_complete":
      return { ...turn, phase: "done", status: turn.error ? turn.status : "complete" };
    case "heartbeat":
      return turn;
  }
}

let liveKeys = 0;

export function Conversation({ id }: { id: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [turns, setTurns] = useState<TurnView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending] = useState(() => takeQuestion(id));
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      apiFetch("/advisor/conversations/{conversation_id}", { params: { conversation_id: id } }),
      apiFetch("/advisor/status"),
    ])
      .then(([loaded, nextStatus]) => {
        if (!live) return;
        setDetail(loaded);
        setStatus(nextStatus);
        setTurns((current) => [...loaded.turns.map(fromStored), ...current]);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, [id]);

  // Leaving the screen stops the answer being written, and its spending.
  useEffect(() => () => controller.current?.abort(), []);

  const update = useCallback((key: string, change: (turn: TurnView) => TurnView) => {
    setTurns((current) => current.map((turn) => (turn.key === key ? change(turn) : turn)));
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const key = `live-${(liveKeys += 1)}`;
      const abort = new AbortController();
      controller.current = abort;
      setTurns((current) => [
        ...current,
        {
          key,
          id: null,
          question,
          status: "streaming",
          phase: "looking",
          text: "",
          answer: null,
          lookups: [],
          error: null,
          feedback: null,
          feedbackNote: null,
        },
      ]);
      try {
        await streamTurn(id, question, {
          signal: abort.signal,
          onEvent: (event) => update(key, (turn) => applyEvent(turn, event)),
        });
      } catch (reason: unknown) {
        if (abort.signal.aborted) {
          update(key, (turn) => ({
            ...turn,
            status: "cancelled",
            phase: "done",
            error: { code: "cancelled", resetsOn: null },
          }));
        } else {
          const code =
            reason instanceof ApiError && reason.status === 409
              ? "turn_in_progress"
              : "model_error";
          update(key, (turn) => ({
            ...turn,
            status: "failed",
            phase: "done",
            error: { code, resetsOn: null },
          }));
        }
      } finally {
        if (controller.current === abort) controller.current = null;
        update(key, (turn) =>
          turn.status === "streaming" ? { ...turn, status: "complete", phase: "done" } : turn,
        );
      }
    },
    [id, update],
  );

  // The first question, a tick after mount: see the module docstring.
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void ask(pending), 0);
    return () => clearTimeout(timer);
  }, [pending, ask]);

  const onFeedback = useCallback(
    (key: string, feedback: TurnView["feedback"], note: string | null) =>
      update(key, (turn) => ({ ...turn, feedback, feedbackNote: note })),
    [update],
  );

  if (detail === null || status === null) {
    if (error) return <ErrorState title="Conversation unavailable" detail={error} />;
    return <Skeleton className="h-64 w-full" />;
  }

  const streaming = turns.some((turn) => turn.status === "streaming");

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold">{detail.title}</h1>
        <p className="text-ink-muted text-xs">
          {detail.view === "mine" ? "Mine" : "Household"} · each person sees only their own
          conversations
        </p>
      </header>

      {turns.map((turn) => (
        <TurnCard
          key={turn.key}
          turn={turn}
          onStop={turn.status === "streaming" ? () => controller.current?.abort() : undefined}
          onFeedback={onFeedback}
        />
      ))}

      {status.enabled ? null : <StatusLine status={status} />}
      <QuestionBox
        onAsk={ask}
        disabled={!status.enabled}
        busy={streaming}
        label="Ask a follow-up"
        placeholder="Ask a follow-up"
      />
    </div>
  );
}
