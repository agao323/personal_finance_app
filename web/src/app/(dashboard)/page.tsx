"use client";

import { NetWorthChart } from "@/components/charts/net-worth-chart";
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

      {/* Not keyed on `view`: the chart refetches on a scope change and holds its
          previous render meanwhile, which is smoother than a remount to skeleton. */}
      <div className="mt-4">
        <ErrorBoundary>
          <NetWorthChart view={view} />
        </ErrorBoundary>
      </div>
    </div>
  );
}
