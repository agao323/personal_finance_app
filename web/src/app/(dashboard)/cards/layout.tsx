"use client";

/**
 * Master–detail shell for the cards area. (Ticket 066)
 *
 * **One component tree; CSS decides the shape.** Above the breakpoint the list and the
 * detail sit side by side. Below it they are separate screens — `/cards` is the list,
 * `/cards/[id]` is that card — which is how master–detail works on a phone without
 * building a second layout and keeping the two in step.
 *
 * The list lives in the layout rather than the page so it is not re-fetched and re-mounted
 * on every card you click.
 */

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { CardList } from "@/components/cards/card-list";
import type { Cards } from "@/components/cards/types";
import { ErrorState, Refreshing, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { CardsContext } from "@/components/cards/context";

export default function CardsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/cards";
  const onDetail = pathname !== "/cards";
  const selectedId = Number(pathname.split("/")[2]) || undefined;

  const [loaded, setLoaded] = useState<{
    key: number;
    cards: Cards | null;
    error: string | null;
  } | null>(null);
  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => setRevision((n) => n + 1), []);

  // **The last response that arrived, kept while the next one is in flight.** (Ticket 070)
  //
  // These three lines are the whole flash. `pending` used to mean "the response I hold
  // answers an older revision", so marking one credit put the list, the detail column and
  // every panel back to skeletons and rebuilt them — a page reload for a one-field change.
  // It now means "nothing has ever arrived", and everything else is a refresh over data
  // that is still on screen.
  const cards = loaded?.cards ?? null;
  const pending = loaded === null;
  const refreshing = loaded !== null && loaded.key !== revision;
  const error = loaded?.error ?? null;

  useEffect(() => {
    let live = true;
    const requested = revision;
    apiFetch("/cards")
      .then((next) => {
        if (live) setLoaded({ key: requested, cards: next, error: null });
      })
      .catch((cause: unknown) => {
        if (live)
          // Keep what is on screen. A refresh that failed has not made the figures wrong,
          // and blanking them loses more than the failure did.
          setLoaded((previous) => ({
            key: requested,
            cards: previous?.cards ?? null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          }));
      });
    return () => {
      live = false;
    };
  }, [revision]);

  return (
    <CardsContext.Provider value={{ cards, pending, refreshing, error, reload, revision }}>
      {/* The title sits above both columns rather than inside each. Two independent
          headers cannot share a baseline once one of them grows — an icon button, a longer
          name — and that misalignment is exactly what it looked like.
          The refresh indicator lives here, in the one place on the screen that never
          moves, rather than inside whichever panel triggered the reload. */}
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-medium tracking-tight">Cards</h1>
        {refreshing ? <Refreshing /> : null}
      </div>

      <div className="mt-4 flex items-start gap-6">
        <aside
          className={`${onDetail ? "hidden md:block" : "block"} w-full shrink-0 md:w-64 lg:w-72`}
        >
          <div className="border-hairline bg-surface-1 overflow-hidden rounded-xl border">
            {pending ? (
              <Skeleton className="h-40 w-full" />
            ) : cards === null ? (
              <div className="p-3">
                <ErrorState detail={error ?? undefined} onRetry={reload} />
              </div>
            ) : (
              <>
                {/* A failure over data that is still good: say so, keep the list. The
                    full-panel error is for a first load that never arrived. */}
                {error ? (
                  <p
                    role="alert"
                    className="text-critical-text border-hairline/60 border-b px-3 py-2 text-xs"
                  >
                    Could not refresh.{" "}
                    <button type="button" onClick={reload} className="underline underline-offset-4">
                      Try again
                    </button>
                  </p>
                ) : null}
                <CardList cards={cards} selectedId={selectedId} onChange={reload} />
              </>
            )}
          </div>
        </aside>

        <main className={`${onDetail ? "block" : "hidden md:block"} min-w-0 flex-1`}>
          {children}
        </main>
      </div>
    </CardsContext.Provider>
  );
}
