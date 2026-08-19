"use client";

/**
 * Record a balance.
 *
 * Every balance write appends a snapshot — history is never reconstructable after the
 * fact, so this form adds a point rather than editing one. Recording the same date
 * twice overwrites that date's snapshot server-side, which is the one case where
 * "append" and "correct a typo" have to be the same action.
 *
 * The date defaults to today and is capped there. A balance dated in the future would
 * become the in-force balance immediately and quietly change today's net worth.
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

export function todayIso(now = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function validateBalance(
  asOf: string,
  cents: number | null,
  today = todayIso(),
): { asOf?: string; amount?: string } {
  const errors: { asOf?: string; amount?: string } = {};
  if (cents === null) errors.amount = "Enter an amount like 1234.56.";
  if (!asOf) errors.asOf = "Pick the date this balance is from.";
  else if (asOf > today) errors.asOf = "A balance cannot be dated in the future.";
  return errors;
}

export function BalanceForm({
  accountId,
  accountName,
  isLiability,
  onRecorded,
}: {
  accountId: number;
  accountName: string;
  isLiability?: boolean;
  onRecorded: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [cents, setCents] = useState<number | null>(null);
  const [asOf, setAsOf] = useState(() => todayIso());
  const [errors, setErrors] = useState<{ asOf?: string; amount?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validateBalance(asOf, cents);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setFailure(null);
    try {
      await apiFetch("/accounts/{account_id}/balances", {
        method: "post",
        params: { account_id: accountId },
        body: { as_of: asOf, balance_cents: cents as number, source: "manual" },
      });
      setDone(asOf);
      setAmount("");
      setCents(null);
      onRecorded();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The balance was not recorded.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Balance"
          error={errors.amount}
          hint={isLiability ? "What you owe, as a positive number." : undefined}
        >
          {({ id, describedBy, invalid }) => (
            <MoneyInput
              id={id}
              value={amount}
              describedBy={describedBy}
              invalid={invalid}
              onChange={(raw, parsed) => {
                setAmount(raw);
                setCents(parsed);
              }}
            />
          )}
        </Field>

        <Field label="As of" error={errors.asOf}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="date"
              value={asOf}
              max={todayIso()}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              onChange={(event) => setAsOf(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
      </div>

      {done ? (
        <p role="status" className="text-ink-secondary mt-3 text-sm">
          Recorded for {accountName} as of {formatDate(done)}.
        </p>
      ) : null}

      <FormActions submitting={submitting} error={failure} submitLabel="Record balance" />
    </form>
  );
}
