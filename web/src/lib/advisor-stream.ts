/**
 * Ask a question and read the answer as it is written.
 *
 * `EventSource` cannot POST, so this is `apiStream()` plus a small server-sent-events reader
 * (docs/ADVISOR.md#request-path). `apiStream` lives beside `apiFetch` in the one fetcher, so
 * the path is relative, through this origin's proxy, never the API directly.
 *
 * **Cancelling is aborting.** The signal aborts this fetch; the proxy forwards the abort to
 * the API (ticket 100); the API cancels the turn and closes the model's stream, so a Stop
 * press or a closed screen stops the spending too.
 */

import { apiStream } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type AdvisorEvent = components["schemas"]["AdvisorEvent"];

/** Split complete `data:` events off the front of a buffer; return them and the remainder. */
export function parseEvents(buffer: string): { events: AdvisorEvent[]; rest: string } {
  const events: AdvisorEvent[] = [];
  const normalised = buffer.replace(/\r\n/g, "\n");
  const blocks = normalised.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (data) events.push(JSON.parse(data) as AdvisorEvent);
  }
  return { events, rest };
}

export async function streamTurn(
  conversationId: string,
  question: string,
  { signal, onEvent }: { signal?: AbortSignal; onEvent: (event: AdvisorEvent) => void },
): Promise<void> {
  const body = await apiStream("/advisor/conversations/{conversation_id}/turns", {
    params: { conversation_id: conversationId },
    body: { question },
    signal,
  });

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseEvents(buffer);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  const last = parseEvents(`${buffer}${decoder.decode()}\n\n`);
  last.events.forEach(onEvent);
}
