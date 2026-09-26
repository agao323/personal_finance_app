/**
 * Inline action icons.
 *
 * Hand-authored SVG rather than an icon package: four small shapes do not justify a
 * dependency, and `currentColor` makes them follow the theme without a second palette to
 * keep in step.
 *
 * **Every icon button needs an accessible name.** An icon alone is unusable with a screen
 * reader and ambiguous with a mouse, so `IconButton` takes a required `label`, exposes it
 * as `aria-label`, and shows it as a native tooltip.
 */

import type { ReactNode } from "react";

export function PencilIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none">
      <path
        d="M11.5 2.5l2 2L5 13l-2.5.5L3 11l8.5-8.5z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none">
      <path
        d="M2.5 4h11M6 4V2.5h4V4M4 4l.6 9.5h6.8L12 4M6.5 6.5v5M9.5 6.5v5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function WarningIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none">
      <path d="M8 2l6 11H2L8 2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M8 6.5v3M8 11.2v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

/** A square icon control with a required accessible name. */
export function IconButton({
  label,
  onClick,
  tone = "neutral",
  children,
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  /** `critical` is for destructive actions only — it is how "this removes things" reads. */
  tone?: "neutral" | "critical";
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`border-hairline hover:bg-surface-2 rounded-md border p-1.5 transition-colors disabled:opacity-50 ${
        tone === "critical" ? "text-critical-text hover:border-critical/40" : "text-ink-secondary"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * A countdown that reads as urgent.
 *
 * Colour amplifies; it never carries the meaning alone. The glyph and the words stay, so
 * this survives a colourblind reader and a monochrome print.
 */
export function ExpiryChip({ label, urgent }: { label: string; urgent: boolean }) {
  if (!urgent) {
    return <span className="text-ink-muted text-xs whitespace-nowrap">{label}</span>;
  }
  return (
    <span className="bg-warning-bg text-warning-text inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap">
      <WarningIcon />
      {label}
    </span>
  );
}
