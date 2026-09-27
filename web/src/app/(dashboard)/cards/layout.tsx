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
import { ErrorState, Skeleton } from "@/components/states";
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

  const cards = loaded?.key === revision && !loaded.error ? loaded.cards : null;
  const pending = loaded?.key !== revision;
  const error = loaded?.key === revision ? loaded.error : null;

  useEffect(() => {
    let live = true;
    const requested = revision;
    apiFetch("/cards")
      .then((next) => {
        if (live) setLoaded({ key: requested, cards: next, error: null });
      })
      .catch((cause: unknown) => {
        if (live)
          setLoaded({
            key: requested,
            cards: null,
            error: cause instanceof Error ? cause.message : "That did not load.",
          });
      });
    return () => {
      live = false;
    };
  }, [revision]);

  return (
    <CardsContext.Provider value={{ cards, pending, error, reload, revision }}>
      {/* The title sits above both columns rather than inside each. Two independent
          headers cannot share a baseline once one of them grows — an icon button, a longer
          name — and that misalignment is exactly what it looked like. */}
      <h1 className="text-xl font-medium tracking-tight">Cards</h1>

      <div className="mt-4 flex items-start gap-6">
        <aside
          className={`${onDetail ? "hidden md:block" : "block"} w-full shrink-0 md:w-64 lg:w-72`}
        >
          <div className="border-hairline bg-surface-1 overflow-hidden rounded-xl border">
            {pending && !error ? (
              <Skeleton className="h-40 w-full" />
            ) : error ? (
              <div className="p-3">
                <ErrorState detail={error} onRetry={reload} />
              </div>
            ) : (
              <CardList cards={cards ?? []} selectedId={selectedId} onChange={reload} />
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
