"use client";

import { useEffect, useState } from "react";

import type { ViewScope } from "@/components/view-toggle";
import { EmptyState, ErrorState, StaleBadge } from "@/components/states";
import { StatTile, StatTileSkeleton } from "@/components/stat-tile";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { computeDelta, formatCurrency } from "@/lib/format";

type NetWorth = ResponseOf<"/net-worth", "get">;

type State =
  | { status: "loading" }
  | { status: "ready"; current: NetWorth; prior: NetWorth | null }
  | { status: "error"; message: string };

function priorMonth(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))
    .toISOString()
    .slice(0, 10);
}

export function NetWorthTile({ view }: { view: ViewScope }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let active = true;

    Promise.all([
      apiFetch("/net-worth", { query: { view } }),
      // A missing prior period is not an error — a brand new install has no
      // history, and the tile still has a current value worth showing.
      apiFetch("/net-worth", { query: { view, as_of: priorMonth() } }).catch(() => null),
    ])
      .then(([current, prior]) => {
        if (active) setState({ status: "ready", current, prior });
      })
      .catch((error: unknown) => {
        if (active) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Unknown error",
          });
        }
      });

    return () => {
      active = false;
    };
  }, [view]);

  if (state.status === "loading") return <StatTileSkeleton label="Net worth" />;
  if (state.status === "error") {
    return <ErrorState title="Net worth unavailable" detail={state.message} />;
  }

  const { current, prior } = state;
  const delta = prior ? computeDelta(current.net_worth_cents, prior.net_worth_cents) : undefined;
  const stale = current.stale_account_ids.length;

  return (
    <StatTile
      label={view === "household" ? "Household net worth" : "Net worth"}
      value={formatCurrency(current.net_worth_cents)}
      delta={delta}
      deltaPeriod="last month"
      badge={stale > 0 ? <StaleBadge asOf={current.as_of} /> : undefined}
      footnote={
        stale > 0
          ? `${stale} account${stale === 1 ? "" : "s"} using a balance over 90 days old`
          : undefined
      }
    >
      <dl className="border-hairline mt-3 grid grid-cols-2 gap-3 border-t pt-3 text-sm">
        <div>
          <dt className="text-ink-secondary">Assets</dt>
          <dd className="mt-0.5">{formatCurrency(current.assets_cents)}</dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Liabilities</dt>
          <dd className="mt-0.5">{formatCurrency(current.liabilities_cents)}</dd>
        </div>
      </dl>
    </StatTile>
  );
}

export function NetWorthEmpty() {
  return (
    <EmptyState
      title="No balances yet"
      detail="Add an account and record a balance to see net worth."
    />
  );
}
