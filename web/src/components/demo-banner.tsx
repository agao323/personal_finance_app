"use client";

/**
 * Says the data is invented.
 *
 * Permanent and above the navigation, not a dismissible toast. Someone arriving on a
 * finance app and seeing plausible balances will assume they belong to whoever built
 * it unless told otherwise, and a banner they dismissed on the dashboard is gone by
 * the time they reach the transactions screen — which is where the figures look most
 * like a real person's life.
 *
 * Renders nothing outside the demo build, and `IS_DEMO` is inlined at build time, so
 * the real bundle does not contain this markup at all.
 */

import { IS_DEMO } from "@/lib/demo";

export function DemoBanner() {
  if (!IS_DEMO) return null;

  return (
    <div className="border-accent/40 bg-accent-bg text-accent-strong border-b px-4 py-2 text-center text-sm">
      <strong className="font-medium">Demo.</strong> Every figure here is generated — no real
      account, balance or transaction. Editing is disabled.
    </div>
  );
}
