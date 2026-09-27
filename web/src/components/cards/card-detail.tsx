"use client";

/**
 * One card, in full. (Tickets 066, 067)
 *
 * **Managing the card itself — renaming, deleting, adding another — lives in the list**,
 * not here. Those act on a card as one item among several, and keeping them in the list
 * means they do not vanish the moment a card is open. Editing the fee stays, because it
 * sits beside the figure it explains.
 *
 * Opens with the compact summary — credits, available, fee, realised — then the credits
 * themselves, then this card's history. No collapsing: this *is* the page, so there is
 * nothing to collapse it out of the way of.
 */

import { useState } from "react";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { FeeForm } from "./fee-form";
import { BackfillForm, HistoryPanel } from "./history";
import { ExpiryChip, HistoryIcon, IconButton, PencilIcon } from "./icons";
import { MarkButton } from "./mark-button";
import { PerkForm, PerkRemoveButton } from "./perk-form";
import { CADENCE_LABELS, CADENCE_ORDER, expiryLabel, type Card, type Perk } from "./types";

export function CardDetail({
  card,
  revision,
  onChange,
}: {
  card: Card;
  revision: number;
  onChange: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [editingFee, setEditingFee] = useState(false);

  const grouped = CADENCE_ORDER.map((cadence) => ({
    cadence,
    perks: card.perks.filter((perk) => perk.cadence === cadence && perk.is_active),
  })).filter((group) => group.perks.length > 0);
  const retired = card.perks.filter((perk) => !perk.is_active);

  return (
    <div>
      {/* Only a way back on a phone, where the list is a separate screen. */}
      <Link
        href="/cards"
        className="text-ink-secondary hover:text-ink mb-3 inline-block text-sm underline underline-offset-4 md:hidden"
      >
        ← All cards
      </Link>

      {/* One panel: the card's name, its figures, and the control for the only figure
          that is editable. Previously the name floated above a bare grid with the fee
          link stranded underneath it, which read as three unrelated things. Its top edge
          lines up with the list beside it because both are the first element in their
          column. */}
      <section className="border-hairline bg-surface-1 overflow-hidden rounded-xl border">
        <header className="border-hairline/60 flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-3">
          <h2 className="flex flex-wrap items-baseline gap-2 text-base font-medium tracking-tight">
            {card.name}
            {card.institution ? (
              <span className="text-ink-muted text-sm font-normal">{card.institution}</span>
            ) : null}
            {card.is_closed ? (
              <span className="border-hairline text-ink-muted rounded border px-1.5 py-px text-[10px] tracking-wide uppercase">
                closed
              </span>
            ) : null}
          </h2>
          <button
            type="button"
            onClick={() => setEditingFee(true)}
            className="border-hairline hover:bg-surface-2 rounded-lg border px-2.5 py-1 text-xs transition-colors"
          >
            {card.annual_fee_cents != null ? "Edit annual fee" : "Add an annual fee"}
          </button>
        </header>

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
          <dl className="grid grid-cols-2 gap-px sm:grid-cols-4">
            <Figure label="Credits" value={String(card.active_perk_count)} />
            <Figure label="Available now" value={formatCurrency(card.unused_cents)} />
            <Figure
              label="Annual fee"
              value={card.annual_fee_cents != null ? formatCurrency(card.annual_fee_cents) : "—"}
            />
            <Figure
              label="Realised this fee year"
              value={
                card.realised_this_fee_year_cents != null
                  ? formatCurrency(card.realised_this_fee_year_cents)
                  : "—"
              }
              detail={card.fee_year_start ? `since ${formatDate(card.fee_year_start)}` : undefined}
            />
          </dl>
        )}
      </section>

      <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        <h2 className="text-sm font-medium">Credits</h2>

        {grouped.length === 0 && retired.length === 0 ? (
          <p className="text-ink-muted mt-2 text-xs">
            None tracked yet. Add the recurring ones — a monthly dining credit, an annual travel
            credit.
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
            {/* Visible, not hidden: a retired credit you cannot see is one you add again. */}
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
      </section>

      <HistoryPanel revision={revision} accountId={card.account_id} />
    </div>
  );
}

function Figure({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-hairline/60 bg-surface-1 border-t px-4 py-2.5 first:border-t-0 sm:border-t-0">
      <dt className="text-ink-muted text-[11px] tracking-wide uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
      {detail ? <dd className="text-ink-muted mt-0.5 text-[11px]">{detail}</dd> : null}
    </div>
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
          {/* Nothing is running out if it has already been used. */}
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
