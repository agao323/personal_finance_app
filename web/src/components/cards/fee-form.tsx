"use client";

/**
 * A card's annual fee. (Tickets 062, 073)
 *
 * The column has existed since 053 and 059 renders the figures, but nothing could set it.
 *
 * **The renewal date is optional.** It used to anchor the window the realised figure was
 * measured against, so leaving it blank meant no figure at all. Since 073 it only says when
 * you next get charged.
 *
 * **Clearing means null, not zero.** A card with no fee recorded shows an em dash; a card
 * with a $0 fee is a different and rarer claim, and conflating them would make "I have not
 * filled this in" indistinguishable from "this card is free".
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
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: clear
          ? { annual_fee_cents: null, fee_renews_on: null }
          : { annual_fee_cents: cents, fee_renews_on: renews || null },
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
          label="Fee charged on (optional)"
          hint="The date the fee hits each year — normally your card's anniversary, not 1 January. Shown beside the fee as the deadline for deciding whether to keep the card. It does not affect what the card reports realising, which is measured on the calendar year."
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
