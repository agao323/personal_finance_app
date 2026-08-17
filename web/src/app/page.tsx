"use client";

/**
 * Connectivity check.
 *
 * Deliberately a client component: it exercises the whole request path the real app
 * uses — browser to this origin, through the proxy route, over the private network
 * to FastAPI. A server component fetching the API directly would skip the proxy and
 * prove less. Ticket 025 replaces this page with the app shell.
 */

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

type State =
  { status: "loading" } | { status: "ok"; body: unknown } | { status: "error"; message: string };

export default function Home() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let active = true;
    apiFetch("/ready")
      .then((body) => active && setState({ status: "ok", body }))
      .catch((error: unknown) =>
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        }),
      );
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Personal Finance</h1>
        <p className="mt-1 text-sm opacity-70">
          Browser → Next.js origin → proxy → FastAPI → Postgres
        </p>
      </header>

      <section
        aria-labelledby="api-status"
        className="rounded-lg border border-black/10 p-4 dark:border-white/15"
      >
        <h2 id="api-status" className="text-sm font-medium">
          API readiness
        </h2>

        {state.status === "loading" && <p className="mt-2 text-sm opacity-70">Checking…</p>}

        {state.status === "ok" && (
          <pre className="mt-2 overflow-x-auto font-mono text-sm">
            {JSON.stringify(state.body, null, 2)}
          </pre>
        )}

        {state.status === "error" && (
          <p role="alert" className="mt-2 font-mono text-sm text-red-600 dark:text-red-400">
            {state.message}
          </p>
        )}
      </section>
    </main>
  );
}
