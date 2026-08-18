"use client";

import { useEffect, useState } from "react";

import { ErrorState } from "@/components/states";
import { StatTile, StatTileSkeleton } from "@/components/stat-tile";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/format";

type Runway = ResponseOf<"/runway", "get">;

type State =
  | { status: "loading" }
  | { status: "ready"; runway: Runway }
  | { status: "error"; message: string };

/** The 6-month window is the headline: 3 is noisy, 12 lags a real change. */
const HEADLINE_WINDOW = 6;

export function RunwayTile() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let active = true;
    apiFetch("/runway")
      .then((runway) => active && setState({ status: "ready", runway }))
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
  }, []);

  if (state.status === "loading") return <StatTileSkeleton label="Runway" />;
  if (state.status === "error") {
    return <ErrorState title="Runway unavailable" detail={state.message} />;
  }

  const { runway } = state;
  const window = runway.windows.find((w) => w.months === HEADLINE_WINDOW) ?? runway.windows[0];

  if (!window) {
    return (
      <StatTile
        label="Runway"
        value="Not enough history"
        footnote="Needs at least one complete month of spending."
      />
    );
  }

  const months = window.months_of_runway;

  return (
    <StatTile
      label="Runway"
      value={months === null || months === undefined ? "—" : `${months.toFixed(1)} months`}
      // The definition has to be on the tile. A runway number whose meaning is
      // ambiguous is worse than no runway number: gross spend answers "how long if
      // income stopped", and netting income in would make it meaningless.
      footnote={`${formatCurrency(window.average_monthly_spend_cents)}/mo gross spend, ${window.months}-month average, transfers excluded${
        runway.partial_month_excluded ? ". Current partial month excluded." : ""
      }`}
    >
      <dl className="border-hairline mt-3 grid grid-cols-2 gap-3 border-t pt-3 text-sm">
        <div>
          <dt className="text-ink-secondary">Liquid assets</dt>
          <dd className="mt-0.5">{formatCurrency(runway.liquid_assets_cents)}</dd>
        </div>
        <div>
          <dt className="text-ink-secondary">Monthly burn</dt>
          <dd className="mt-0.5">{formatCurrency(window.average_monthly_spend_cents)}</dd>
        </div>
      </dl>
    </StatTile>
  );
}
