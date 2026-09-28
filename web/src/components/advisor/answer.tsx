"use client";

/**
 * One question and its answer: the text as it is written, then the checked version with
 * every figure marked, its sources, what the app could not answer, the lookups behind it,
 * and a way to flag it.
 *
 * **Nothing here can make the browser fetch.** Text is drawn from `markdown-lite`'s tree,
 * which has no node for a link or an image; screen tokens become buttons that route inside
 * the app. `answer.test.tsx` plants the EchoLeak shapes and asserts no `a` and no `img`.
 *
 * **Controls sit on the answer they act on**: Stop beside the answer being written, the
 * flag and "show lookups" under the answer they describe.
 */

import { useRouter } from "next/navigation";
import { Fragment, memo, useState, type ReactNode } from "react";

import { REASONS, type AdvisorErrorCode } from "@/lib/advisor";
import { apiFetch } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { formatDate } from "@/lib/format";
import { parse, type Block, type Inline, type Span } from "@/lib/markdown-lite";
import { screenRoute, type Screen } from "@/lib/screens";

export type Answer = components["schemas"]["Answer"];
export type Lookup = components["schemas"]["Lookup"];
export type Citation = components["schemas"]["Citation"];
export type FigureCheck = components["schemas"]["FigureCheck"];
export type Feedback = components["schemas"]["Feedback"];
type LimitationKind = components["schemas"]["LimitationKind"];

/** A turn as the screen holds it: from the stored conversation, or being written now. */
export type TurnView = {
  key: string;
  id: string | null;
  question: string;
  status: "streaming" | "complete" | "cancelled" | "failed" | "refused";
  /** While streaming: `looking` until text arrives, `checking` until `answer`. */
  phase: "looking" | "writing" | "checking" | "regenerating" | "done";
  text: string;
  answer: Answer | null;
  lookups: Lookup[];
  error: { code: AdvisorErrorCode; resetsOn: string | null } | null;
  feedback: Feedback | null;
  feedbackNote: string | null;
};

const LIMITATIONS: Record<LimitationKind, string> = {
  holdings: "The app has no holdings — it tracks account balances, not what is in them.",
  tax_treatment: "The app does not know each account's tax treatment yet.",
  liability_terms: "The app has no liability terms yet — rates, payments, payoff dates.",
  goals: "The app has no goals yet.",
  credit_limits: "The app does not know your credit limits.",
  reward_multipliers: "The app does not know each card's reward rates.",
  credit_score: "The app does not track a credit score.",
  income_history: "The app has too little income history for that.",
  balance_history: "The app has too little balance history for that.",
  transaction_coverage: "Some accounts' transactions are not imported far enough.",
  projections: "The app cannot project that yet.",
  market_data: "The app has no market data — prices, rates or news.",
  tax_or_legal_advice: "That needs a tax professional or an attorney.",
  other: "The app does not have the data for part of this.",
};

const SCREEN_LABELS: Record<Screen, string> = {
  dashboard: "Dashboard",
  spending: "Spending",
  transactions: "Transactions",
  accounts: "Accounts",
  account: "Accounts",
  cards: "Cards",
  import: "Import",
  rules: "Rules",
  goals: "Goals",
  planning: "Planning",
  advisor: "Advisor",
};

// ── text ──────────────────────────────────────────────────────────────────────

type FigureContext = { figures: FigureCheck[]; citations: Citation[] };

function ScreenButton({ screen }: { screen: Screen }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => router.push(screenRoute(screen))}
      className="bg-accent-bg text-accent-strong mx-0.5 rounded px-1.5 py-0.5 text-xs font-medium"
    >
      Open {SCREEN_LABELS[screen]}
    </button>
  );
}

function FigureMark({
  text,
  check,
  citations,
}: {
  text: string;
  check: FigureCheck;
  citations: Citation[];
}) {
  const [open, setOpen] = useState(false);
  if (check.status === "matched") return <>{text}</>;
  if (check.status === "unverified") {
    return (
      <span className="inline">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-critical-text decoration-critical underline decoration-wavy underline-offset-2"
        >
          {text}
        </button>
        <span className="text-critical-text ml-0.5 text-[11px]">unverified</span>
        {open ? <span className="text-ink-secondary ml-1 text-xs">({check.reason})</span> : null}
      </span>
    );
  }
  const source = citations.find((c) => c.call_id === check.source?.call_id);
  return (
    <span className="inline">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="decoration-ink-muted underline decoration-dotted underline-offset-2"
      >
        {text}
      </button>
      {open ? (
        <span className="text-ink-secondary ml-1 text-xs">
          (from {source ? source.label : check.source?.call_id}
          {source?.as_of ? `, as of ${formatDate(source.as_of)}` : ""})
        </span>
      ) : null}
    </span>
  );
}

function renderInline(nodes: Inline[], context: FigureContext | null): ReactNode {
  return nodes.map((node, index) => {
    switch (node.type) {
      case "text":
        return <Fragment key={index}>{node.text}</Fragment>;
      case "strong":
        return <strong key={index}>{renderInline(node.children, context)}</strong>;
      case "em":
        return <em key={index}>{renderInline(node.children, context)}</em>;
      case "code":
        return (
          <code key={index} className="bg-surface-2 rounded px-1 text-[0.9em]">
            {node.text}
          </code>
        );
      case "screen":
        return <ScreenButton key={index} screen={node.screen} />;
      case "figure": {
        const check = context?.figures[node.index];
        if (!check) return <Fragment key={index}>{node.text}</Fragment>;
        return (
          <FigureMark key={index} text={node.text} check={check} citations={context.citations} />
        );
      }
    }
  });
}

function renderBlocks(blocks: Block[], context: FigureContext | null): ReactNode {
  return blocks.map((block, index) => {
    switch (block.type) {
      case "paragraph":
        return <p key={index}>{renderInline(block.children, context)}</p>;
      case "heading":
        return block.level === 3 ? (
          <h3 key={index} className="font-semibold">
            {renderInline(block.children, context)}
          </h3>
        ) : (
          <h4 key={index} className="font-medium">
            {renderInline(block.children, context)}
          </h4>
        );
      case "list": {
        const items = block.items.map((item, i) => <li key={i}>{renderInline(item, context)}</li>);
        return block.ordered ? (
          <ol key={index} className="list-decimal pl-5">
            {items}
          </ol>
        ) : (
          <ul key={index} className="list-disc pl-5">
            {items}
          </ul>
        );
      }
      case "table":
        return (
          <div key={index} className="overflow-x-auto">
            <table className="text-sm">
              <thead>
                <tr>
                  {block.header.map((cell, i) => (
                    <th
                      key={i}
                      className="border-hairline border-b px-2 py-1 text-left font-medium"
                    >
                      {renderInline(cell, context)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, i) => (
                      <td key={i} className="px-2 py-1 tabular-nums">
                        {renderInline(cell, context)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
    }
  });
}

/** Answer text, drawn from `markdown-lite`'s tree. Figures carry their checks when given. */
export function AnswerText({ text, answer }: { text: string; answer?: Answer | null }) {
  const spans: Span[] = answer ? answer.figures.map((f) => ({ start: f.start, end: f.end })) : [];
  const context = answer ? { figures: answer.figures, citations: answer.citations } : null;
  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed">
      {renderBlocks(parse(text, spans), context)}
    </div>
  );
}

// ── around the text ───────────────────────────────────────────────────────────

function Sources({ answer }: { answer: Answer }) {
  if (answer.citations.length === 0 && answer.limitations.length === 0) return null;
  return (
    <div className="border-hairline mt-3 border-t pt-2 text-xs">
      {answer.citations.length > 0 ? (
        <ul aria-label="Sources" className="text-ink-secondary flex flex-col gap-0.5">
          {answer.citations.map((c) => (
            <li key={c.call_id}>
              {c.label}
              {c.as_of ? ` · as of ${formatDate(c.as_of)}` : ""}
              {c.view ? ` · ${c.view === "mine" ? "Mine" : "Household"}` : ""}
              {c.stale ? (
                <span className="bg-warning-bg text-warning-text ml-1 rounded px-1">Stale</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {answer.limitations.length > 0 ? (
        <ul
          aria-label="What the app could not answer"
          className="text-ink mt-2 flex flex-col gap-0.5"
        >
          {answer.limitations.map((kind) => (
            <li key={kind}>{LIMITATIONS[kind]}</li>
          ))}
        </ul>
      ) : null}
      {answer.policy_notes.map((note) => (
        <p key={note.check} className="text-warning-text mt-2">
          {note.message}
        </p>
      ))}
    </div>
  );
}

function Lookups({ lookups }: { lookups: Lookup[] }) {
  const [open, setOpen] = useState(false);
  if (lookups.length === 0) return null;
  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-ink-secondary hover:text-ink underline underline-offset-4"
      >
        {open ? "Hide lookups" : `Show lookups (${lookups.length})`}
      </button>
      {open ? (
        <ul aria-label="Lookups" className="text-ink-secondary mt-1 flex flex-col gap-1">
          {lookups.map((lookup) => (
            <li key={lookup.call_id} className="tabular-nums">
              <span className="text-ink">{lookup.label}</span> ·{" "}
              {lookup.arguments || "no arguments"} · {lookup.row_count}{" "}
              {lookup.row_count === 1 ? "row" : "rows"} · {lookup.latency_ms} ms
              {lookup.status !== "ok" ? ` · ${lookup.status.replace("_", " ")}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function FeedbackControl({
  turnId,
  feedback,
  note,
  onSaved,
}: {
  turnId: string;
  feedback: Feedback | null;
  note: string | null;
  onSaved: (feedback: Feedback, note: string | null) => void;
}) {
  const [flagging, setFlagging] = useState(false);
  const [draft, setDraft] = useState(note ?? "");
  const [error, setError] = useState<string | null>(null);

  async function save(verdict: Feedback, withNote: string | null) {
    setError(null);
    try {
      await apiFetch("/advisor/turns/{turn_id}/feedback", {
        method: "put",
        params: { turn_id: turnId },
        body: { verdict, note: withNote },
      });
      onSaved(verdict, withNote);
      setFlagging(false);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Not saved.");
    }
  }

  return (
    <div className="mt-2 text-xs">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-pressed={feedback === "good"}
          onClick={() => void save("good", null)}
          className={
            feedback === "good"
              ? "text-accent-strong font-medium"
              : "text-ink-secondary hover:text-ink"
          }
        >
          Good answer
        </button>
        <button
          type="button"
          aria-pressed={feedback === "flagged"}
          onClick={() => setFlagging((v) => !v)}
          className={
            feedback === "flagged"
              ? "text-warning-text font-medium"
              : "text-ink-secondary hover:text-ink"
          }
        >
          {feedback === "flagged" ? "Flagged" : "Flag"}
        </button>
      </div>
      {flagging ? (
        <div className="mt-2 flex flex-col gap-1">
          <label htmlFor={`note-${turnId}`} className="text-ink-secondary">
            What was wrong? (optional)
          </label>
          <textarea
            id={`note-${turnId}`}
            value={draft}
            maxLength={500}
            onChange={(event) => setDraft(event.target.value)}
            rows={2}
            className="border-hairline bg-surface-1 rounded-md border px-2 py-1"
          />
          <button
            type="button"
            onClick={() => void save("flagged", draft.trim() || null)}
            className="bg-accent-bg text-accent-strong self-start rounded px-2 py-1 font-medium"
          >
            Save flag
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-critical-text mt-1">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ErrorLine({ error }: { error: NonNullable<TurnView["error"]> }) {
  return (
    <p role="alert" className="text-critical-text text-sm">
      {REASONS[error.code]}
      {error.code === "monthly_cap" && error.resetsOn
        ? ` It resets on ${formatDate(error.resetsOn)}.`
        : ""}
    </p>
  );
}

const PHASES: Record<TurnView["phase"], string | null> = {
  looking: "Looking things up…",
  writing: null,
  checking: "Checking figures…",
  regenerating: "Rewriting so every figure can be checked…",
  done: null,
};

/**
 * A turn. Memoised on the turn object, so text streaming into the newest turn does not
 * re-render the ones above it.
 */
export const TurnCard = memo(function TurnCard({
  turn,
  onStop,
  onFeedback,
}: {
  turn: TurnView;
  onStop?: () => void;
  onFeedback: (key: string, feedback: Feedback, note: string | null) => void;
}) {
  const streaming = turn.status === "streaming";
  const phase = PHASES[turn.phase];
  return (
    <article aria-label={turn.question} className="flex flex-col gap-2">
      <p className="bg-accent-bg text-ink self-end rounded-xl px-3 py-2 text-sm">{turn.question}</p>
      <div className="border-hairline bg-surface-1 rounded-xl border p-3">
        {streaming && turn.lookups.length > 0 ? (
          <ul aria-label="Looking up" className="text-ink-muted mb-2 flex flex-col gap-0.5 text-xs">
            {turn.lookups.map((lookup) => (
              <li key={lookup.call_id}>{lookup.label}</li>
            ))}
          </ul>
        ) : null}

        {turn.answer ? (
          <AnswerText text={turn.answer.text} answer={turn.answer} />
        ) : turn.text ? (
          <AnswerText text={turn.text} />
        ) : null}

        {streaming && phase ? (
          <p role="status" className="text-ink-muted mt-2 text-xs">
            {phase}
          </p>
        ) : null}
        {turn.answer?.truncated ? (
          <p className="text-warning-text mt-2 text-xs">This answer was cut off.</p>
        ) : null}
        {turn.error ? <ErrorLine error={turn.error} /> : null}
        {streaming && onStop ? (
          <button
            type="button"
            onClick={onStop}
            className="border-hairline hover:bg-surface-2 mt-2 rounded-lg border px-3 py-1 text-xs"
          >
            Stop
          </button>
        ) : null}

        {turn.answer ? <Sources answer={turn.answer} /> : null}
        {!streaming ? <Lookups lookups={turn.lookups} /> : null}
        {!streaming && turn.answer && turn.id ? (
          <FeedbackControl
            turnId={turn.id}
            feedback={turn.feedback}
            note={turn.feedbackNote}
            onSaved={(feedback, note) => onFeedback(turn.key, feedback, note)}
          />
        ) : null}
      </div>
    </article>
  );
});
