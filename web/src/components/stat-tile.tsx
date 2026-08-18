"use client";

/**
 * The stat tile.
 *
 * Contract: label (sentence case, no trailing colon) · value (the number, large,
 * proportional figures) · optional delta (signed, against a *named* period) ·
 * optional footnote.
 *
 * Two rules worth stating because both are easy to get wrong:
 *
 * Direction is not carried by colour. Each delta ships an arrow glyph and names its
 * comparison period, so a colourblind reader and a printed page lose nothing. And
 * "up" is not universally good — a rising liability is bad — so the caller declares
 * which direction is favourable rather than the tile assuming.
 *
 * Values use the font's default proportional figures. `tabular-nums` gives every
 * digit the width of a zero, which looks loose at display sizes; it belongs in
 * columns that must align vertically, not here.
 */

import type { ReactNode } from "react";

import type { Delta } from "@/lib/format";
import { Skeleton } from "@/components/states";

export function StatTile({
  label,
  value,
  delta,
  deltaPeriod,
  upIsGood = true,
  footnote,
  badge,
  children,
}: {
  label: string;
  value: string;
  delta?: Delta;
  deltaPeriod?: string;
  upIsGood?: boolean;
  footnote?: string;
  badge?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="border-hairline bg-surface-1 rounded-xl border p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-ink-secondary text-sm">{label}</p>
        {badge}
      </div>

      <p className="mt-2 text-3xl font-medium tracking-tight">{value}</p>

      {delta ? <DeltaLine delta={delta} period={deltaPeriod} upIsGood={upIsGood} /> : null}
      {footnote ? <p className="text-ink-muted mt-2 text-xs">{footnote}</p> : null}
      {children}
    </div>
  );
}

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function DeltaLine({
  delta,
  period,
  upIsGood,
}: {
  delta: Delta;
  period?: string;
  upIsGood: boolean;
}) {
  const good = delta.direction === "flat" ? null : (delta.direction === "up") === upIsGood;
  const tone = good === null ? "text-ink-secondary" : good ? "text-delta-up" : "text-delta-down";

  return (
    <p className={`mt-1 flex items-baseline gap-1.5 text-sm ${tone}`}>
      <span aria-hidden="true">{ARROW[delta.direction]}</span>
      <span>{delta.absolute}</span>
      {delta.percent ? <span>({delta.percent})</span> : null}
      {period ? <span className="text-ink-muted">vs {period}</span> : null}
    </p>
  );
}

/** Placeholder shaped like the tile it replaces, so the layout never jumps. */
export function StatTileSkeleton({ label }: { label: string }) {
  return (
    <div className="border-hairline bg-surface-1 rounded-xl border p-4">
      <p className="text-ink-secondary text-sm">{label}</p>
      <Skeleton className="mt-3 h-9 w-40" />
      <Skeleton className="mt-2 h-4 w-28" />
    </div>
  );
}
