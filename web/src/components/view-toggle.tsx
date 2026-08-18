"use client";

/**
 * Mine / Household.
 *
 * The entire multi-user surface of the app. "Mine" applies the viewer's ownership
 * stake; "Household" sums every stake — so a 50%-owned rental contributes half or
 * all of its value depending on this switch.
 *
 * Persisted to localStorage rather than a URL param: it is a durable preference
 * about how you read your own numbers, not a property of a particular page, and
 * having it reset on every navigation would be maddening.
 */

import { useCallback, useSyncExternalStore } from "react";

import type { components } from "@/lib/api-types";

export type ViewScope = components["schemas"]["ViewScope"];

const STORAGE_KEY = "pfa:view-scope";
const DEFAULT: ViewScope = "mine";

/**
 * localStorage is not always there.
 *
 * Safari in private mode, storage disabled by policy, and a full quota all make
 * these throw or return null. A dashboard must not go blank because a display
 * preference could not be read — it falls back to "mine" and carries on.
 */
function read(): ViewScope {
  try {
    const value = globalThis.localStorage?.getItem(STORAGE_KEY);
    return value === "mine" || value === "household" ? value : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

function write(value: ViewScope): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, value);
  } catch {
    // Not persisted this session. Not worth surfacing to the user.
  }
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changing the preference should update this one.
  globalThis.addEventListener?.("storage", listener);
  return () => {
    listeners.delete(listener);
    globalThis.removeEventListener?.("storage", listener);
  };
}

/**
 * `useSyncExternalStore` rather than an effect that calls setState.
 *
 * Reading storage in an effect and then setting state renders twice on every mount
 * and trips React's cascading-render rule. This is the API React provides for
 * exactly this shape — external mutable source, server snapshot for SSR.
 */
export function useViewScope(): [ViewScope, (next: ViewScope) => void] {
  const view = useSyncExternalStore(subscribe, read, () => DEFAULT);

  const update = useCallback((next: ViewScope) => {
    write(next);
    for (const listener of listeners) listener();
  }, []);

  return [view, update];
}

const OPTIONS: { value: ViewScope; label: string }[] = [
  { value: "mine", label: "Mine" },
  { value: "household", label: "Household" },
];

export function ViewToggle({
  view,
  onChange,
}: {
  view: ViewScope;
  onChange: (next: ViewScope) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Whose money to show"
      className="border-hairline bg-surface-1 inline-flex rounded-lg border p-0.5"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={view === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-md px-3 py-1 text-sm transition-colors ${
            view === option.value
              ? "bg-accent-bg text-accent-strong font-medium"
              : "text-ink-secondary hover:text-ink"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
