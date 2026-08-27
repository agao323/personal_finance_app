"use client";

/**
 * Credit cards and the perks on them.
 *
 * **Expiring first, then everything else.** The question this page answers is "what am
 * I about to lose", and a list of cards you had to read down to work that out would be
 * a worse version of the spreadsheet it replaces.
 *
 * Marking a perk used is optimistic. This gets pressed on a phone, in a restaurant, on
 * a bad connection — a spinner blocking the row is a worse experience than a state that
 * is wrong for 200ms and then corrects itself visibly.
 */

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";

type Cards = ResponseOf<"/cards", "get">;
type Card = Cards[number];
type Perk = Card["perks"][number];
type Upcoming = ResponseOf<"/perks/upcoming", "get">;

const CADENCES = ["monthly", "quarterly", "semiannual", "annual"] as const;
type Cadence = (typeof CADENCES)[number];

const CADENCE_LABELS: Record<Cadence, string> = {
  monthly: "Monthly",
  quarterly: "Quarterly",
  semiannual: "Every 6 months",
  annual: "Annual",
};

/**
 * How urgent a deadline reads.
 *
 * "Expires in 0 days" is a sentence nobody parses at a glance, and it is the one that
 * matters most. `days_remaining` is 0 on the final day — the API is explicit about that
 * so this does not have to guess.
 */
export function expiryLabel(daysRemaining: number): string {
  if (daysRemaining <= 0) return "Today";
  if (daysRemaining === 1) return "Tomorrow";
  if (daysRemaining < 7) return `${daysRemaining} days`;
  if (daysRemaining < 14) return "Next week";
  return `${daysRemaining} days`;
}

export default function CardsPage() {
  const [cards, setCards] = useState<Cards | null>(null);
  const [upcoming, setUpcoming] = useState<Upcoming | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => setRevision((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    Promise.all([apiFetch("/cards"), apiFetch("/perks/upcoming", { query: { within_days: 45 } })])
      .then(([cardList, soon]) => {
        if (!live) return;
        setCards(cardList);
        setUpcoming(soon);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (live) setError(cause instanceof Error ? cause.message : "That did not work.");
      });
    return () => {
      live = false;
    };
  }, [revision]);

  return (
    <div>
      <h1 className="text-xl font-medium tracking-tight">Cards</h1>

      {error ? <ErrorState detail={error} onRetry={reload} /> : null}

      <ExpiringSoon upcoming={upcoming} onChange={reload} />

      {cards === null && !error ? (
        <Skeleton className="mt-4 h-40 w-full" />
      ) : cards !== null && cards.length === 0 ? (
        <EmptyState
          title="No credit cards yet"
          detail="Add a credit card account, then its perks will live here."
        />
      ) : (
        (cards ?? []).map((card) => (
          <CardPanel key={card.account_id} card={card} onChange={reload} />
        ))
      )}
    </div>
  );
}

function ExpiringSoon({ upcoming, onChange }: { upcoming: Upcoming | null; onChange: () => void }) {
  if (upcoming === null) return null;

  if (upcoming.perks.length === 0) {
    return (
      <p className="text-ink-secondary mt-3 text-sm">
        Nothing expiring in the next {upcoming.within_days} days.
      </p>
    );
  }

  return (
    <section className="border-warning/40 bg-surface-1 mt-4 rounded-xl border p-4">
      <h2 className="text-sm font-medium">
        {formatCurrency(upcoming.total_cents)} expiring in the next {upcoming.within_days} days
      </h2>
      <ul className="mt-3">
        {upcoming.perks.map((row) => (
          <li
            key={row.perk.id}
            className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-2 last:border-0"
          >
            <span className="text-sm">
              <span className="block font-medium">{row.perk.name}</span>
              <span className="text-ink-muted block text-xs">
                {row.card_name} · {formatCurrency(row.perk.value_cents)}
              </span>
            </span>
            <span className="flex items-center gap-3 text-sm">
              <span className="text-warning-text text-xs font-medium">
                {expiryLabel(row.perk.current_period?.days_remaining ?? 0)}
              </span>
              <MarkButton perk={row.perk} onChange={onChange} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CardPanel({ card, onChange }: { card: Card; onChange: () => void }) {
  const [adding, setAdding] = useState(false);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">
          {card.name}
          {card.is_closed ? (
            <span className="border-hairline text-ink-muted ml-2 rounded border px-1.5 py-px text-[10px] tracking-wide uppercase">
              closed
            </span>
          ) : null}
        </h2>
        <span className="text-ink-secondary text-xs">
          {formatCurrency(card.unused_cents)} unused this period
        </span>
      </div>

      {card.perks.length === 0 ? (
        <p className="text-ink-muted mt-2 text-xs">No perks tracked on this card yet.</p>
      ) : (
        <ul className="mt-2">
          {card.perks.map((perk) => (
            <PerkRow key={perk.id} perk={perk} onChange={onChange} />
          ))}
        </ul>
      )}

      {adding ? (
        <AddPerkForm
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
          Add a perk
        </button>
      )}
    </section>
  );
}

function PerkRow({ perk, onChange }: { perk: Perk; onChange: () => void }) {
  const period = perk.current_period;

  return (
    <li className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-sm">
        <span className="block font-medium">
          {perk.name}
          {!perk.is_active ? (
            <span className="text-ink-muted ml-2 text-[10px] tracking-wide uppercase">retired</span>
          ) : null}
        </span>
        <span className="text-ink-muted block text-xs">
          {formatCurrency(perk.value_cents)} · {CADENCE_LABELS[perk.cadence as Cadence]}
          {period ? ` · resets ${formatDate(period.end)}` : " · not started yet"}
        </span>
      </span>
      {period ? <MarkButton perk={perk} onChange={onChange} /> : null}
    </li>
  );
}

/**
 * Mark used, or undo.
 *
 * Optimistic: the label flips immediately and reverts if the request fails. `pending`
 * holds the value we are hoping for, so a failure has something to fall back from
 * rather than guessing at what the server now thinks.
 */
function MarkButton({ perk, onChange }: { perk: Perk; onChange: () => void }) {
  const used = perk.current_period?.is_used ?? false;
  const [pending, setPending] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);
  const shown = pending ?? used;

  async function toggle() {
    const next = !shown;
    setPending(next);
    setFailed(false);
    try {
      // Two calls rather than one with a computed method: DELETE takes no body, so a
      // `post | delete` union narrows `body` to `undefined` and the POST stops
      // type-checking. Splitting is less clever and actually compiles.
      if (next) {
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "post",
          params: { perk_id: perk.id },
          body: {},
        });
      } else {
        await apiFetch("/perks/{perk_id}/redemptions", {
          method: "delete",
          params: { perk_id: perk.id },
        });
      }
      onChange();
    } catch {
      setPending(null);
      setFailed(true);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {failed ? (
        <span role="alert" className="text-critical-text text-xs">
          Did not save
        </span>
      ) : null}
      <button
        type="button"
        onClick={toggle}
        aria-pressed={shown}
        className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
          shown ? "bg-accent-bg text-accent-strong" : "border-hairline hover:bg-surface-2 border"
        }`}
      >
        {shown ? "Used" : "Mark used"}
      </button>
    </span>
  );
}

function AddPerkForm({
  accountId,
  onDone,
  onCancel,
}: {
  accountId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [valueCents, setValueCents] = useState<number | null>(null);
  const [cadence, setCadence] = useState<Cadence>("annual");
  const [anchor, setAnchor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const cents = valueCents;
    if (cents === null || cents <= 0) {
      setError("Enter what the perk is worth, like 200 or 12.50.");
      return;
    }
    if (!anchor) {
      setError("Enter the date this perk's first period began.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/cards/{account_id}/perks", {
        method: "post",
        params: { account_id: accountId },
        body: { name, value_cents: cents, cadence, anchor_on: anchor },
      });
      onDone();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That perk was not added.");
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
              {CADENCES.map((option) => (
                <option key={option} value={option}>
                  {CADENCE_LABELS[option]}
                </option>
              ))}
            </select>
          )}
        </Field>
        {/* The label alone is meaningless — nobody guesses what an anchor date is.
            The hint is doing the actual work here and is not decoration. */}
        <Field
          label="First period began"
          hint="1 January for a credit that resets on the calendar year, or the day you opened the card if it resets on your cardmember year."
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
      <FormActions submitting={busy} error={error} submitLabel="Add perk" onCancel={onCancel} />
    </form>
  );
}
