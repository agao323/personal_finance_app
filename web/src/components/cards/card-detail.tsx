"use client";

/**
 * One card, in full. (Tickets 066, 067, 072)
 *
 * **Acting on this card happens on this card.** Renaming and deleting sit in the summary
 * panel's header; the fee control sits inside the fee figure it edits. 066 had the first two
 * in the list so they would not disappear when a card was open, and the fee button in the
 * header rather than next to the number — both put a control somewhere other than the thing
 * it acts on, which is the only reason you have to look for it.
 *
 * Adding a card stays in the list, because it acts on the list.
 *
 * Opens with the compact summary — credits, available, fee, realised — then the credits
 * themselves, then this card's history. No collapsing: this *is* the page, so there is
 * nothing to collapse it out of the way of.
 */

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { FeeForm } from "./fee-form";
import { HistoryPanel } from "./history";
import { ExpiryChip, HistoryIcon, IconButton, PencilIcon, TrashIcon } from "./icons";
import { MarkButton } from "./mark-button";
import { PeriodGrid } from "./period-grid";
import { PerkForm, PerkRemoveButton } from "./perk-form";
import { RemoveCard } from "./remove-card";
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
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [editingFee, setEditingFee] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [removing, setRemoving] = useState(false);

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

      {/* One panel: the card's name, the controls that act on the card, and its figures.
          Its top edge lines up with the list beside it because both are the first element
          in their column. */}
      <section className="border-hairline bg-surface-1 overflow-hidden rounded-xl border">
        <header className="border-hairline/60 flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-3">
          {renaming ? (
            <CardNameForm
              card={card}
              onDone={() => {
                setRenaming(false);
                onChange();
              }}
              onCancel={() => setRenaming(false)}
            />
          ) : (
            <>
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
              <span className="flex shrink-0 items-center gap-1">
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
              </span>
            </>
          )}
        </header>

        {removing ? (
          <div className="border-hairline/60 border-b p-4">
            <RemoveCard
              card={card}
              onDone={() => {
                setRemoving(false);
                onChange();
                // This card no longer exists, and staying here would render "No such
                // card" — a dead end where the reader's own action put them.
                router.push("/cards");
              }}
              onCancel={() => setRemoving(false)}
            />
          </div>
        ) : null}

        <dl className="grid grid-cols-2 gap-px sm:grid-cols-4">
          <Figure label="Credits" value={String(card.active_perk_count)} />
          <Figure label="Available now" value={formatCurrency(card.unused_cents)} />
          <Figure
            label="Annual fee"
            value={card.annual_fee_cents != null ? formatCurrency(card.annual_fee_cents) : "—"}
            // Beside the number it edits, rather than in the panel header. A control
            // somewhere other than the thing it acts on is a control you have to look for.
            action={
              <button
                type="button"
                onClick={() => setEditingFee((current) => !current)}
                className="text-accent text-[11px] underline underline-offset-4"
              >
                {card.annual_fee_cents != null ? "Edit" : "Add"}
              </button>
            }
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

        {/* Below the figures, not instead of them: the fee year and the realised figure are
            what you are editing against. */}
        {editingFee ? (
          <div className="border-hairline/60 border-t px-4 pb-4">
            <FeeForm
              card={card}
              onDone={() => {
                setEditingFee(false);
                onChange();
              }}
              onCancel={() => setEditingFee(false)}
            />
          </div>
        ) : null}
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
                  revision={revision}
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
                  revision={revision}
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

function Figure({
  label,
  value,
  detail,
  action,
}: {
  label: string;
  value: string;
  detail?: string;
  /** A control for this figure, sitting with it rather than in the panel header. */
  action?: ReactNode;
}) {
  return (
    <div className="border-hairline/60 bg-surface-1 border-t px-4 py-2.5 first:border-t-0 sm:border-t-0">
      <dt className="text-ink-muted text-[11px] tracking-wide uppercase">{label}</dt>
      <dd className="mt-0.5 flex items-baseline gap-2 text-sm font-medium tabular-nums">
        {value}
        {action}
      </dd>
      {detail ? <dd className="text-ink-muted mt-0.5 text-[11px]">{detail}</dd> : null}
    </div>
  );
}

/** Rename the card, in place in the header where its name is. */
function CardNameForm({
  card,
  onDone,
  onCancel,
}: {
  card: Card;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(card.name);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!name.trim() || name === card.name) {
      onCancel();
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: card.account_id },
        body: { name },
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <label className="sr-only" htmlFor={`rename-${card.account_id}`}>
        Card name
      </label>
      <input
        id={`rename-${card.account_id}`}
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="border-hairline bg-surface-1 w-full rounded-md border px-2 py-1 text-sm"
      />
      <span className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="bg-accent-bg text-accent-strong rounded-lg px-2.5 py-1 text-sm font-medium disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </span>
    </div>
  );
}

function PerkRowItem({
  accountId,
  perk,
  revision,
  onChange,
}: {
  accountId: number;
  perk: Perk;
  revision: number;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [showingPeriods, setShowingPeriods] = useState(false);
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
            label={`Which periods you used ${perk.name} in — tap a month to record one you forgot`}
            onClick={() => setShowingPeriods((current) => !current)}
          >
            <HistoryIcon />
          </IconButton>
          <PerkRemoveButton perk={perk} onDone={onChange} />
        </span>
      </div>
      {/* Stays open while you fill in a year: each tap saves on its own, so closing after
          one would be closing after every one. */}
      {showingPeriods ? <PeriodGrid perk={perk} revision={revision} onChange={onChange} /> : null}
    </li>
  );
}
