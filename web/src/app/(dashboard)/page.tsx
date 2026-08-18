"use client";

import { ErrorBoundary } from "@/components/states";
import { NetWorthTile } from "@/components/tiles/net-worth";
import { RunwayTile } from "@/components/tiles/runway";
import { ViewToggle, useViewScope } from "@/components/view-toggle";

export default function DashboardPage() {
  const [view, setView] = useViewScope();

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-medium tracking-tight">Dashboard</h1>
        <ViewToggle view={view} onChange={setView} />
      </div>

      {/* Boundaries are per tile: one failing endpoint must not blank the other. */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {/* key={view} remounts the tile on a scope change, so it returns to its
            loading state without a setState inside an effect. */}
        <ErrorBoundary key={view}>
          <NetWorthTile view={view} />
        </ErrorBoundary>
        <ErrorBoundary>
          <RunwayTile />
        </ErrorBoundary>
      </div>
    </div>
  );
}
