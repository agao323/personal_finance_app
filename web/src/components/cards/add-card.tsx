"use client";

/**
 * Add a card, in card language. (Ticket 067)
 *
 * The list used to say *"a card is an account with the credit card subtype"* and link to
 * the account form. Both halves were wrong for the reader: the sentence explains the
 * schema, and that form only reaches a credit card after you pick "liability" as the Kind
 * — while its own copy steers you toward importing a CSV instead.
 *
 * **The storage does not change and should not.** A card's balance is debt that has to
 * count in net worth, so it is an account underneath; a separate table would either
 * duplicate those rows or drop cards out of the figure. What changes is that nobody has to
 * learn that to add one. The liability kind, the credit-card subtype and the full ownership
 * stake are filled in here.
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { apiFetch } from "@/lib/api";

export function AddCard({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [issuer, setIssuer] = useState("");
  const [fee, setFee] = useState("");
  const [feeCents, setFeeCents] = useState<number | null>(null);
  const [renews, setRenews] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Give the card a name — whatever you call it.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiFetch("/accounts", {
        method: "post",
        body: {
          name,
          kind: "liability",
          subtype: "credit_card",
          ...(issuer.trim() ? { institution_name: issuer } : {}),
          // Every account gets an explicit stake at creation; there is no implicit
          // "no row means fully owned" default. See ARCHITECTURE#users-and-ownership.
          ownership_percentage_bps: 10_000,
        },
      });

      // The fee is a separate concern from creating the card, so it is a follow-up rather
      // than a required field — most people will not know the renewal date on day one.
      if (feeCents !== null && feeCents > 0 && renews) {
        await apiFetch("/accounts/{account_id}", {
          method: "patch",
          params: { account_id: created.id },
          body: { annual_fee_cents: feeCents, fee_renews_on: renews },
        });
      }
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That card was not added.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="p-3">
      <h2 className="text-sm font-medium">Add a card</h2>
      <div className="mt-3 grid gap-3">
        <Field label="Card name" hint="Whatever you call it — Platinum, the blue one.">
          {({ id, describedBy }) => (
            <input
              id={id}
              type="text"
              value={name}
              aria-describedby={describedBy}
              onChange={(event) => setName(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="Issuer" hint="Optional.">
          {({ id, describedBy }) => (
            <input
              id={id}
              type="text"
              value={issuer}
              aria-describedby={describedBy}
              onChange={(event) => setIssuer(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="Annual fee" hint="Optional — you can add it later.">
          {({ id, describedBy }) => (
            <MoneyInput
              id={id}
              value={fee}
              describedBy={describedBy}
              onChange={(raw, cents) => {
                setFee(raw);
                setFeeCents(cents);
              }}
            />
          )}
        </Field>
        {feeCents !== null && feeCents > 0 ? (
          <Field label="Fee charged on" hint="Normally the card's anniversary, not 1 January.">
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
        ) : null}
      </div>
      <FormActions submitting={busy} error={error} submitLabel="Add card" onCancel={onCancel} />
    </form>
  );
}
