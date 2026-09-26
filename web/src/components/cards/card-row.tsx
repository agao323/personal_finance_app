"use client";

/**
 * One card, with its whole state visible before you expand it. (Ticket 055)
 *
 * MaxRewards' Wallet row is the pattern: name, what is available, and how many credits —
 * so a wallet of six cards is scannable without opening any of them.
 *
 * Perks inside are grouped by cadence, monthly first, because a monthly credit recurs most
 * often and so gets checked most often.
 */

import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { FeeForm } from "./fee-form";
import { BackfillForm } from "./history";
import { ExpiryChip, HistoryIcon, IconButton, PencilIcon, TrashIcon } from "./icons";
import { MarkButton } from "./mark-button";
import { NetValue } from "./net-value";
import { PerkForm, PerkRemoveButton } from "./perk-form";
import { RemoveCard } from "./remove-card";
import { CADENCE_LABELS, CADENCE_ORDER, expiryLabel, type Card, type Perk } from "./types";

export function CardRow({ card, onChange }: { card: Card; onChange: () => void }) {
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [editingFee, setEditingFee] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [name, setName] = useState(card.name);

  async function rename() {
    if (!name.trim() || name === card.name) {
      setRenaming(false);
      return;
    }
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: { name },
      });
      onChange();
    } finally {
      setRenaming(false);
    }
  }

  const grouped = CADENCE_ORDER.map((cadence) => ({
    cadence,
    perks: card.perks.filter((perk) => perk.cadence === cadence && perk.is_active),
  })).filter((group) => group.perks.length > 0);
  const retired = card.perks.filter((perk) => !perk.is_active);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        {renaming ? (
          <span className="flex items-center gap-2">
            <label className="sr-only" htmlFor={`name-${card.account_id}`}>
              Card name
            </label>
            <input
              id={`name-${card.account_id}`}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="border-hairline bg-surface-1 rounded-md border px-2 py-1 text-sm"
            />
            <button
              type="button"
              onClick={() => void rename()}
              className="bg-accent-bg text-accent-strong rounded-lg px-2.5 py-1 text-sm font-medium"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setName(card.name);
                setRenaming(false);
              }}
              className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
            >
              Cancel
            </button>
          </span>
        ) : (
          <h2 className="flex flex-wrap items-baseline gap-2 text-sm font-medium">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpen((current) => !current)}
              className="hover:text-accent flex items-center gap-1.5"
            >
              <span aria-hidden="true" className="text-ink-muted text-xs">
                {open ? "▾" : "▸"}
              </span>
              {card.name}
            </button>
            {card.institution ? (
              <span className="text-ink-muted text-xs font-normal">{card.institution}</span>
            ) : null}
            {card.is_closed ? (
              <span className="border-hairline text-ink-muted rounded border px-1.5 py-px text-[10px] tracking-wide uppercase">
                closed
              </span>
            ) : null}
          </h2>
        )}

        <span className="flex items-center gap-2">
          <span className="text-ink-secondary text-xs tabular-nums">
            {formatCurrency(card.unused_cents)} available ·{" "}
            {card.active_perk_count === 1 ? "1 credit" : `${card.active_perk_count} credits`}
          </span>
          {!renaming ? (
            <>
              <IconButton label={`Rename ${card.name}`} onClick={() => setRenaming(true)}>
                <PencilIcon />
              </IconButton>
              <IconButton
                label={`Delete ${card.name} and all of its history — balances, transactions and credits`}
                tone="critical"
                onClick={() => setRemoving(true)}
              >
                <TrashIcon />
              </IconButton>
            </>
          ) : null}
        </span>
      </div>

      {editingFee ? (
        <FeeForm
          card={card}
          onDone={() => {
            setEditingFee(false);
            onChange();
          }}
          onCancel={() => setEditingFee(false)}
        />
      ) : (
        <>
          <NetValue card={card} />
          <button
            type="button"
            onClick={() => setEditingFee(true)}
            className="text-ink-secondary hover:text-ink mt-2 text-xs underline underline-offset-4"
          >
            {card.annual_fee_cents != null ? "Edit annual fee" : "Add an annual fee"}
          </button>
        </>
      )}

      {removing ? (
        <RemoveCard
          card={card}
          onDone={() => {
            setRemoving(false);
            onChange();
          }}
          onCancel={() => setRemoving(false)}
        />
      ) : null}

      {open ? (
        <>
          {grouped.length === 0 && retired.length === 0 ? (
            <p className="text-ink-muted mt-3 text-xs">
              No credits tracked on this card yet. Add the recurring ones — a monthly dining credit,
              an annual travel credit.
            </p>
          ) : null}

          {grouped.map((group) => (
            <div key={group.cadence} className="mt-3">
              <h3 className="text-ink-muted text-[11px] font-medium tracking-wide uppercase">
                {CADENCE_LABELS[group.cadence]}
              </h3>
              <ul className="mt-1">
                {group.perks.map((perk) => (
                  <PerkRowItem
                    key={perk.id}
                    accountId={card.account_id}
                    perk={perk}
                    onChange={onChange}
                  />
                ))}
              </ul>
            </div>
          ))}

          {retired.length > 0 ? (
            <div className="mt-3">
              <h3 className="text-ink-muted text-[11px] font-medium tracking-wide uppercase">
                Retired
              </h3>
              {/* Visible, not hidden: a retired credit you cannot see is one you will add
                  again by mistake. */}
              <ul className="mt-1">
                {retired.map((perk) => (
                  <PerkRowItem
                    key={perk.id}
                    accountId={card.account_id}
                    perk={perk}
                    onChange={onChange}
                  />
                ))}
              </ul>
            </div>
          ) : null}

          {adding ? (
            <PerkForm
              accountId={card.account_id}
              onDone={() => {
                setAdding(false);
                onChange();
              }}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="border-hairline hover:bg-surface-2 mt-3 rounded-lg border px-3 py-1.5 text-sm transition-colors"
            >
              Add a credit
            </button>
          )}
        </>
      ) : null}
    </section>
  );
}

function PerkRowItem({
  accountId,
  perk,
  onChange,
}: {
  accountId: number;
  perk: Perk;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const period = perk.current_period;

  if (editing) {
    return (
      <li className="py-2">
        <PerkForm
          accountId={accountId}
          perk={perk}
          onDone={() => {
            setEditing(false);
            onChange();
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className="border-hairline/60 border-b py-2 last:border-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm">
          <span className="block font-medium">{perk.name}</span>
          <span className="text-ink-muted block text-xs">
            {formatCurrency(perk.value_cents)}
            {period ? (
              <>
                {" · resets "}
                {formatDate(period.end)}

                {period.is_used && period.used_amount_cents != null ? (
                  <> · used {formatCurrency(period.used_amount_cents)}</>
                ) : null}
              </>
            ) : (
              " · has not started yet"
            )}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-2 text-sm">
          {/* Nothing is running out if it has already been used. A countdown on a spent
              credit is noise at best and a contradiction at worst. */}
          {period && !period.is_used ? (
            <ExpiryChip label={expiryLabel(period.days_remaining)} urgent={period.is_urgent} />
          ) : null}
          {period && perk.is_active ? <MarkButton perk={perk} onChange={onChange} /> : null}
          <IconButton
            label={`Edit ${perk.name} — its value, how often it resets, or when its first period began`}
            onClick={() => setEditing(true)}
          >
            <PencilIcon />
          </IconButton>
          <IconButton
            label={`Record a past use of ${perk.name} — for a credit you spent earlier and never marked`}
            onClick={() => setBackfilling((current) => !current)}
          >
            <HistoryIcon />
          </IconButton>
          <PerkRemoveButton perk={perk} onDone={onChange} />
        </span>
      </div>
      {backfilling ? (
        <BackfillForm
          perkId={perk.id}
          onDone={() => {
            setBackfilling(false);
            onChange();
          }}
          onCancel={() => setBackfilling(false)}
        />
      ) : null}
    </li>
  );
}
