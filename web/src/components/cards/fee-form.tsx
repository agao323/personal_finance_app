"use client";

/**
 * A card's annual fee. (Ticket 062)
 *
 * The column has existed since 053 and 059 renders the figures, but nothing could set it.
 *
 * **Clearing means null, not zero.** A card with no fee recorded shows no net-value panel
 * at all; a card with a $0 fee is a different and rarer claim, and conflating them would
 * make "I have not filled this in" indistinguishable from "this card is free".
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { apiFetch } from "@/lib/api";
import { centsToInputValue } from "@/lib/format";
import type { Card } from "./types";

export function FeeForm({
  card,
  onDone,
  onCancel,
}: {
  card: Card;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(
    card.annual_fee_cents != null ? centsToInputValue(card.annual_fee_cents) : "",
  );
  const [cents, setCents] = useState<number | null>(card.annual_fee_cents ?? null);
  const [renews, setRenews] = useState(card.fee_renews_on ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(clear = false) {
    if (!clear) {
      if (cents === null || cents < 0) {
        setError("Enter the fee, like 695 or 0.");
        return;
      }
      if (!renews) {
        setError("Enter the date the fee is charged each year.");
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: clear
          ? { annual_fee_cents: null, fee_renews_on: null }
          : { annual_fee_cents: cents, fee_renews_on: renews },
      });
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
      noValidate
      className="border-hairline mt-3 rounded-lg border p-3"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Annual fee">
          {({ id, describedBy }) => (
            <MoneyInput
              id={id}
              value={value}
              describedBy={describedBy}
              onChange={(raw, parsed) => {
                setValue(raw);
                setCents(parsed);
              }}
            />
          )}
        </Field>
        <Field
          label="Fee charged on"
          hint="The date the fee hits each year — normally your card's anniversary, not 1 January. It sets the fee year the realised figure is measured against, which is why a calendar-year credit and an anniversary fee year can happily disagree."
        >
          {({ id, describedBy }) => (
            <input
              id={id}
              type="date"
              value={renews}
              aria-describedby={describedBy}
              onChange={(event) => setRenews(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
      </div>
      <FormActions submitting={busy} error={error} submitLabel="Save fee" onCancel={onCancel} />
      {card.annual_fee_cents != null ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void save(true)}
          className="text-ink-secondary hover:text-ink mt-2 text-sm underline underline-offset-4 disabled:opacity-50"
        >
          Remove the fee
        </button>
      ) : null}
    </form>
  );
}
