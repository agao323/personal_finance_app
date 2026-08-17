/**
 * Sentry initialisation for the web service.
 *
 * Cleanly disabled when `SENTRY_DSN` is unset, so local development and tests never
 * emit events or make a network call.
 *
 * The DSN is read from a **server-only** variable on purpose. A `NEXT_PUBLIC_`
 * counterpart would ship the DSN to the browser and, more importantly, would start
 * sending client-side breadcrumbs — which on this app means URLs and DOM text
 * containing balances. Errors are reported from the server, where the proxy already
 * sees every request.
 */

import * as Sentry from "@sentry/nextjs";

/** Field names whose values are money. Mirrors `api/app/logging.py`. */
const MONETARY = /(^|_)(amount|balance|total|net_?worth|price|cost|value|income|spend)s?$/i;

function redact(input: unknown): unknown {
  if (Array.isArray(input)) return input.map(redact);
  if (input && typeof input === "object") {
    return Object.fromEntries(
      Object.entries(input as Record<string, unknown>).map(([key, value]) => [
        key,
        MONETARY.test(key) ? "[redacted]" : redact(value),
      ]),
    );
  }
  return input;
}

let initialised = false;

/** Initialise Sentry. Returns whether it was enabled. Safe to call more than once. */
export function initSentry(dsn: string | undefined = process.env.SENTRY_DSN): boolean {
  if (!dsn) return false;
  if (initialised) return true;

  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend(event) {
      // Request payloads never leave. On this app a request body is a balance.
      if (event.request) {
        delete event.request.data;
        delete event.request.cookies;
        delete event.request.query_string;
      }
      return redact(event) as typeof event;
    },
  });

  initialised = true;
  return true;
}

export const __testing = { redact, MONETARY };
