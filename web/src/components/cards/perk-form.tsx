"use client";

/**
 * Add, edit, or remove a credit. (Ticket 057)
 *
 * One component for all three, because they are the same fields — a separate edit form
 * would drift from the add form the first time a field changed.
 *
 * **Delete and retire are different actions that look alike.** Delete is for the credit
 * you added by mistake. Retire is for one the card stopped offering, and it keeps the
 * redemptions recording what you actually used. The API refuses to delete a credit with
 * history and says so; this surfaces *its* message rather than a local paraphrase that
 * could drift from the rule.
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { apiFetch } from "@/lib/api";
import { centsToInputValue } from "@/lib/format";
import { IconButton, TrashIcon } from "./icons";
import { CADENCE_LABELS, CADENCE_ORDER, type Cadence, type Perk } from "./types";

export function PerkForm({
  accountId,
  perk,
  onDone,
  onCancel,
}: {
  accountId: number;
  /** Absent means add. Present means edit, prefilled. */
  perk?: Perk;
  onDone: () => void;
  onCancel: () => void;
}) {
  const editing = perk !== undefined;

  const [name, setName] = useState(perk?.name ?? "");
  const [value, setValue] = useState(perk ? centsToInputValue(perk.value_cents) : "");
  const [valueCents, setValueCents] = useState<number | null>(perk?.value_cents ?? null);
  const [cadence, setCadence] = useState<Cadence>((perk?.cadence as Cadence) ?? "annual");
  const [anchor, setAnchor] = useState(perk?.anchor_on ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cadenceOrAnchorChanged = editing && (cadence !== perk.cadence || anchor !== perk.anchor_on);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Give the credit a name.");
      return;
    }
    if (valueCents === null || valueCents <= 0) {
      setError("Enter what the credit is worth, like 200 or 12.50.");
      return;
    }
    if (!anchor) {
      setError("Enter a date one of this credit's periods starts on.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (editing) {
        await apiFetch("/perks/{perk_id}", {
          method: "patch",
          params: { perk_id: perk.id },
          body: { name, value_cents: valueCents, cadence, anchor_on: anchor },
        });
      } else {
        await apiFetch("/cards/{account_id}/perks", {
          method: "post",
          params: { account_id: accountId },
          body: { name, value_cents: valueCents, cadence, anchor_on: anchor },
        });
      }
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="border-hairline mt-3 rounded-lg border p-3">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          {({ id }) => (
            <input
              id={id}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="Value" hint="What it is worth each period.">
          {({ id, describedBy }) => (
            <MoneyInput
              id={id}
              value={value}
              describedBy={describedBy}
              onChange={(raw, cents) => {
                setValue(raw);
                setValueCents(cents);
              }}
            />
          )}
        </Field>
        <Field label="Resets">
          {({ id }) => (
            <select
              id={id}
              value={cadence}
              onChange={(event) => setCadence(event.target.value as Cadence)}
              className={inputClass}
            >
              {CADENCE_ORDER.map((option) => (
                <option key={option} value={option}>
                  {CADENCE_LABELS[option]}
                </option>
              ))}
            </select>
          )}
        </Field>
        {/* The label alone is meaningless and a wrong value here silently shifts every
            period for this credit. The hint is doing the work.

            It used to say "First period began" and invite the day you opened the card, and
            then the grid treated that date as the beginning of history — so a credit set up
            in August offered two months and refused the rest. Ticket 076 made the anchor a
            phase reference only, and this copy stops implying otherwise. */}
        <Field
          label="Resets on"
          hint="Any date one of this credit's periods starts — it sets where the reset falls, not when the credit began. 1 January for a credit that resets on the calendar year, or your card's anniversary if it resets on the cardmember year. Earlier periods can still be recorded."
        >
          {({ id, describedBy }) => (
            <input
              id={id}
              type="date"
              value={anchor}
              aria-describedby={describedBy}
              onChange={(event) => setAnchor(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
      </div>

      {cadenceOrAnchorChanged ? (
        <p className="text-ink-secondary mt-3 text-xs">
          Existing history keeps the periods it was recorded against. That is deliberate — a
          recorded use is a fact about a date — but it means old entries will not line up with the
          new schedule.
        </p>
      ) : null}

      <FormActions
        submitting={busy}
        error={error}
        submitLabel={editing ? "Save changes" : "Add credit"}
        onCancel={onCancel}
      />
    </form>
  );
}

/**
 * Remove a credit, falling back to retiring it when it has history.
 *
 * Two clicks, never one: there is no undo for a delete, and the confirm step is where the
 * "this has history" refusal surfaces.
 */
export function PerkRemoveButton({ perk, onDone }: { perk: Perk; onDone: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    setRefusal(null);
    try {
      await apiFetch("/perks/{perk_id}", { method: "delete", params: { perk_id: perk.id } });
      onDone();
    } catch (cause: unknown) {
      // The 409 body explains that the credit has recorded uses and names retiring as the
      // alternative. Shown verbatim — a local copy of that rule would drift from it.
      setRefusal(cause instanceof Error ? cause.message : "That could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  async function retire() {
    setBusy(true);
    try {
      await apiFetch("/perks/{perk_id}", {
        method: "patch",
        params: { perk_id: perk.id },
        body: { is_active: !perk.is_active },
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  if (!perk.is_active) {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={retire}
        className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4 disabled:opacity-50"
      >
        Un-retire
      </button>
    );
  }

  if (refusal) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <span role="alert" className="text-critical-text text-xs">
          {refusal}
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={retire}
          className="border-hairline hover:bg-surface-2 rounded-lg border px-2.5 py-1 text-sm disabled:opacity-50"
        >
          Retire instead
        </button>
      </span>
    );
  }

  if (confirming) {
    return (
      <span className="flex items-center gap-2 text-sm">
        <span className="text-ink-secondary text-xs">Remove permanently?</span>
        <button
          type="button"
          disabled={busy}
          onClick={remove}
          className="text-critical-text underline underline-offset-4 disabled:opacity-50"
        >
          Remove
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="text-ink-secondary hover:text-ink underline underline-offset-4"
        >
          Keep
        </button>
      </span>
    );
  }

  return (
    <IconButton
      label={`Remove ${perk.name} — only possible while it has no recorded uses`}
      tone="critical"
      onClick={() => setConfirming(true)}
    >
      <TrashIcon />
    </IconButton>
  );
}
