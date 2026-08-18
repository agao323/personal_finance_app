"use client";

/**
 * The states every screen needs.
 *
 * Loading, error, empty, and stale are not afterthoughts on a finance dashboard: a
 * blank panel and a panel showing zero look identical, and one of them means "you
 * have no money".
 */

import { Component, type ReactNode } from "react";

import { formatAge } from "@/lib/format";

/**
 * A shaped placeholder, not a spinner.
 *
 * A spinner over blank space says nothing about what is coming. A block the size of
 * the value that will replace it keeps the layout from jumping and makes the wait
 * feel shorter.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`bg-hairline animate-pulse rounded ${className}`}
    />
  );
}

export function ErrorState({
  title = "Could not load this",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="border-critical/30 rounded-xl border p-4">
      <p className="text-critical-text text-sm font-medium">{title}</p>
      {detail ? <p className="text-ink-secondary mt-1 text-sm">{detail}</p> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="text-accent mt-3 text-sm underline underline-offset-4"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="border-hairline rounded-xl border border-dashed p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      {detail ? <p className="text-ink-secondary mx-auto mt-1 max-w-sm text-sm">{detail}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

/**
 * Marks a value carried forward from a snapshot older than 90 days.
 *
 * Icon plus label, never colour alone — a status colour carrying meaning by hue is
 * invisible to a colourblind reader and to anyone printing the page. The visible
 * text says *how* old, because "stale" without a magnitude is not actionable.
 */
export function StaleBadge({ asOf, now }: { asOf: string; now?: Date }) {
  return (
    <span
      title={`Last updated ${asOf}`}
      className="text-warning border-warning/40 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" className="h-3 w-3 fill-current">
        <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm.75 3.5v4h-1.5v-4h1.5zm0 5.5v1.5h-1.5V10h1.5z" />
      </svg>
      Updated {formatAge(asOf, now)}
    </span>
  );
}

interface BoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Stops one broken panel from blanking the whole dashboard.
 *
 * A class component because React offers no hook equivalent — `getDerivedStateFromError`
 * is the only way to catch a render error.
 */
export class ErrorBoundary extends Component<BoundaryProps, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <ErrorState
            title="Something went wrong"
            detail={this.state.error.message}
            onRetry={() => this.setState({ error: null })}
          />
        )
      );
    }
    return this.props.children;
  }
}
