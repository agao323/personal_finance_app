/**
 * Next.js instrumentation hook — runs once per server process, before any request.
 *
 * Only the Node.js runtime is wired up: the proxy route and every page render happen
 * there, and the edge runtime is unused in this app.
 */

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { initSentry } = await import("@/lib/sentry");
    initSentry();
  }
}
