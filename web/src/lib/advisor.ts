/**
 * Small pieces the advisor's screens share.
 *
 * **A new conversation's first question travels in sessionStorage, never the URL.** A
 * question can name an amount or a merchant, and a URL is kept in browser history and in
 * every proxy's request log. The list screen stashes it; the conversation screen sends it
 * once and clears it.
 */

import type { components } from "@/lib/api-types";

export type AdvisorStatus = components["schemas"]["AdvisorStatus"];
export type AdvisorErrorCode = components["schemas"]["AdvisorErrorCode"];
export type ConversationSummary = components["schemas"]["ConversationSummary"];

/** The server's limit on a question, in characters. */
export const QUESTION_LIMIT = 2000;
/** The count appears once a question is this close to the limit. */
export const COUNT_FROM = 1800;

const PENDING_KEY = (conversationId: string) => `pfa:advisor:pending:${conversationId}`;

export function stashQuestion(conversationId: string, question: string): void {
  try {
    globalThis.sessionStorage?.setItem(PENDING_KEY(conversationId), question);
  } catch {
    // Storage refused (private mode, quota). The conversation opens empty instead.
  }
}

/** The stashed first question, removed as it is read so a reload cannot send it twice. */
export function takeQuestion(conversationId: string): string | null {
  try {
    const key = PENDING_KEY(conversationId);
    const question = globalThis.sessionStorage?.getItem(key) ?? null;
    globalThis.sessionStorage?.removeItem(key);
    return question;
  } catch {
    return null;
  }
}

/** Every refusal the advisor can give, in words a person can act on. */
export const REASONS: Record<AdvisorErrorCode, string> = {
  disabled: "The advisor is switched off.",
  demo: "The demo shows recorded answers; it never asks a model.",
  not_configured: "The advisor has no model configured yet.",
  monthly_cap: "This month's advisor budget is used up.",
  conversation_cap: "This conversation has reached its budget. Start a new one.",
  turn_cap: "That question reached its budget before an answer was ready.",
  turn_in_progress: "An answer is still being written in this conversation.",
  budget_exhausted: "That question used all its lookups.",
  timeout: "The answer took too long and was stopped.",
  refusal: "The model declined to answer that question.",
  truncated: "The answer was cut off before a lookup it needed could run.",
  cancelled: "Stopped.",
  model_error: "The model could not be reached. Try again in a moment.",
};
