"use client";

/**
 * Shared form furniture.
 *
 * Two things every form here needs and neither is worth writing four times: a field
 * that ties its label, its error, and its control together with real ids, and a money
 * input that submits integer cents.
 *
 * Errors are wired with `aria-describedby` and `aria-invalid` rather than only shown
 * in red. A message a sighted user reads and a screen reader user does not is not an
 * error message, it is decoration.
 */

import { useId, type ReactNode } from "react";

import { parseDollarsToCents } from "@/lib/format";

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string | null;
  hint?: ReactNode;
  /** Receives the ids to bind — the caller owns the control. */
  children: (props: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div>
      <label htmlFor={id} className="text-ink-secondary mb-1 block text-sm">
        {label}
      </label>
      {children({ id, describedBy: describedBy || undefined, invalid: Boolean(error) })}
      {hint ? (
        <p id={hintId} className="text-ink-muted mt-1 text-xs">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-critical-text mt-1 text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  "border-hairline bg-surface-1 text-ink w-full rounded-md border px-2 py-1.5 text-sm aria-[invalid=true]:border-critical";

/**
 * A dollars input that reports integer cents.
 *
 * `type="text"`, not `type="number"`: a number input silently discards what it cannot
 * parse, so a typo becomes an empty field with no message, and its spinner arrows on
 * a balance are an invitation to nudge a figure by a cent. Validation happens on the
 * string, where the problem can be described.
 */
export function MoneyInput({
  id,
  value,
  onChange,
  describedBy,
  invalid,
  placeholder = "0.00",
}: {
  id: string;
  /** The raw text. The form owns it, so a half-typed "12." is not destroyed. */
  value: string;
  onChange: (raw: string, cents: number | null) => void;
  describedBy?: string;
  invalid?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <span className="text-ink-muted pointer-events-none absolute top-1.5 left-2 text-sm">$</span>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value, parseDollarsToCents(event.target.value))}
        className={`${inputClass} pl-5 tabular-nums`}
      />
    </div>
  );
}

/** Submit plus a status line, so a failure is never only in the console. */
export function FormActions({
  submitting,
  error,
  submitLabel,
  onCancel,
}: {
  submitting: boolean;
  error: string | null;
  submitLabel: string;
  onCancel?: () => void;
}) {
  return (
    <div className="mt-4">
      {error ? (
        <p role="alert" className="text-critical-text mb-2 text-sm">
          {error}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          {submitting ? "Saving…" : submitLabel}
        </button>
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
          >
            Cancel
          </button>
        ) : null}
      </div>
    </div>
  );
}
