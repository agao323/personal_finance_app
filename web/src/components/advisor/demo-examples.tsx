"use client";

/**
 * The demo's advisor: recorded conversations, replayed read-only (ADR 0014).
 *
 * The public demo never calls a model — no key, no endpoint, no way to spend. It shows what
 * the advisor does with answers recorded on synthetic data and checked by the same loop, drawn
 * by the same safe renderer as a live answer. There is no question box, and the screen says
 * so plainly rather than pretending.
 *
 * `lib/advisor-examples.json` starts as one recorded example; `make eval-examples` (ticket 102)
 * replaces it with chosen, passing eval transcripts.
 */

import { TurnCard, type Answer, type Lookup, type TurnView } from "@/components/advisor/answer";
import examples from "@/lib/advisor-examples.json";

export type Example = { id: string; question: string; answer: Answer; lookups: Lookup[] };

export const EXAMPLES = examples as Example[];

function asTurn(example: Example): TurnView {
  return {
    key: example.id,
    // No id: a recorded answer cannot be flagged, because there is no turn to flag.
    id: null,
    question: example.question,
    status: "complete",
    phase: "done",
    text: example.answer.text,
    answer: example.answer,
    lookups: example.lookups,
    error: null,
    feedback: null,
    feedbackNote: null,
  };
}

const noFeedback = () => undefined;

export const DEMO_LABEL =
  "Recorded on the demo's synthetic data. This demo cannot ask new questions.";

export function DemoExamples({ examples: shown = EXAMPLES }: { examples?: Example[] }) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold">Advisor</h1>
        <p className="border-hairline bg-surface-2 rounded-lg border px-3 py-2 text-sm">
          {DEMO_LABEL}
        </p>
      </header>
      {shown.map((example) => (
        <TurnCard key={example.id} turn={asTurn(example)} onFeedback={noFeedback} />
      ))}
    </div>
  );
}
