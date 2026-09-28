"use client";

/**
 * Where a question is typed. Used to start a conversation and to continue one.
 *
 * The limit is the server's, 2,000 characters; the count appears only near it, where it is
 * news. Disabled — with the reason shown above it by the caller — whenever the advisor
 * cannot answer.
 */

import { useState } from "react";

import { COUNT_FROM, QUESTION_LIMIT } from "@/lib/advisor";

const grouped = new Intl.NumberFormat("en-US");

export function QuestionBox({
  onAsk,
  disabled = false,
  busy = false,
  label = "Ask about your money",
  placeholder = "What did we spend on dining this quarter?",
  submitLabel = "Ask",
}: {
  onAsk: (question: string) => Promise<void> | void;
  disabled?: boolean;
  busy?: boolean;
  label?: string;
  placeholder?: string;
  submitLabel?: string;
}) {
  const [question, setQuestion] = useState("");
  const trimmed = question.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!trimmed || disabled || busy) return;
    await onAsk(trimmed);
    setQuestion("");
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-2">
      <label htmlFor="advisor-question" className="sr-only">
        {label}
      </label>
      <textarea
        id="advisor-question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        maxLength={QUESTION_LIMIT}
        rows={3}
        disabled={disabled}
        placeholder={placeholder}
        className="border-hairline bg-surface-1 w-full resize-y rounded-lg border px-3 py-2 text-sm disabled:opacity-50"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-ink-muted text-xs tabular-nums" aria-live="polite">
          {question.length >= COUNT_FROM
            ? `${grouped.format(question.length)} / ${grouped.format(QUESTION_LIMIT)}`
            : null}
        </span>
        <button
          type="submit"
          disabled={disabled || busy || !trimmed}
          className="bg-accent-bg text-accent-strong rounded-lg px-4 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
