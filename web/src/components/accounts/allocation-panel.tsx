"use client";

/**
 * What an investment account holds by asset class, recorded per account rather than per holding
 * (ADR 0013), and every change to it.
 *
 * "Unknown" is a real answer and is shown as one: the advisor treats an account with nothing
 * recorded as unknown rather than guessing, and so does this panel. The form will not save
 * unless the classes total exactly 100% — the server refuses anything else, and a Save button
 * that is live on 99.99% is a promise the next click breaks.
 *
 * A new allocation starts on a date and closes the one before it on that date. The history shows
 * each range as the days it covered: ranges are half-open, so the readable end is the day before
 * the next one starts.
 */

import { useEffect, useState } from "react";

import { Field, inputClass } from "@/components/forms/fields";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatBps, formatDate } from "@/lib/format";

export type Allocation = ResponseOf<"/accounts/{account_id}/allocations", "get">;
export type AssetClass = Allocation["shares"][number]["asset_class"];

export const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  us_equity: "US stocks",
  intl_equity: "International stocks",
  bonds: "Bonds",
  cash: "Cash",
  real_estate: "Real estate",
  other: "Other",
};

const CLASSES = Object.keys(ASSET_CLASS_LABELS) as AssetClass[];

type Percents = Record<AssetClass, string>;

const EMPTY: Percents = {
  us_equity: "",
  intl_equity: "",
  bonds: "",
  cash: "",
  real_estate: "",
  other: "",
};

/** Starting points, not advice: each fills the form, which can then be edited. */
export const PRESETS: { label: string; percents: Partial<Percents> }[] = [
  {
    label: "Target-date 2055 ≈ 90/10",
    percents: { us_equity: "54", intl_equity: "36", bonds: "10" },
  },
  { label: "100% cash", percents: { cash: "100" } },
];

/** "39.99" → 3999; null when it is not a percent with at most two decimals. */
export function percentBps(text: string): number | null {
  const trimmed = text.trim().replace(/%$/, "");
  if (!/^\d{1,3}(\.\d{0,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

/**
 * The shares to save and their total, or why they cannot be saved. Blank and zero classes are
 * left out, as the server wants them.
 */
export function readPercents(percents: Percents): {
  shares: { asset_class: AssetClass; percentage_bps: number }[];
  totalBps: number;
  problem: string | null;
} {
  const shares: { asset_class: AssetClass; percentage_bps: number }[] = [];
  let totalBps = 0;
  for (const assetClass of CLASSES) {
    const text = percents[assetClass];
    if (!text.trim()) continue;
    const bps = percentBps(text);
    if (bps === null) {
      return {
        shares,
        totalBps,
        problem: `Enter ${ASSET_CLASS_LABELS[assetClass]} like 40 or 12.5.`,
      };
    }
    if (bps > 0) shares.push({ asset_class: assetClass, percentage_bps: bps });
    totalBps += bps;
  }
  const problem =
    totalBps === 10_000 ? null : `The classes total ${formatBps(totalBps)}; they must total 100%.`;
  return { shares, totalBps, problem };
}

function percentsFrom(allocation: Allocation): Percents {
  const percents = { ...EMPTY };
  if (allocation.status === "recorded") {
    for (const share of allocation.shares) {
      percents[share.asset_class] = formatBps(share.percentage_bps).replace("%", "");
    }
  }
  return percents;
}

function rangeText(from: string, to: string | null | undefined): string {
  if (!to) return `${formatDate(from)} — now`;
  const end = new Date(`${to}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() - 1);
  return `${formatDate(from)} — ${formatDate(end.toISOString().slice(0, 10))}`;
}

/** History rows grouped into the allocations they were set as, newest first. */
function changes(allocation: Allocation) {
  const groups = new Map<string, { from: string; to: string | null; parts: string[] }>();
  for (const row of allocation.history) {
    const group = groups.get(row.effective_from) ?? {
      from: row.effective_from,
      to: row.effective_to ?? null,
      parts: [],
    };
    group.parts.push(`${ASSET_CLASS_LABELS[row.asset_class]} ${formatBps(row.percentage_bps)}`);
    groups.set(row.effective_from, group);
  }
  return [...groups.values()];
}

export function AllocationPanel({
  accountId,
  today = new Date().toISOString().slice(0, 10),
}: {
  accountId: number;
  today?: string;
}) {
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts/{account_id}/allocations", { params: { account_id: accountId } })
      .then((data) => {
        if (live) setAllocation(data);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [accountId]);

  if (allocation?.status === "not_applicable") return null;

  return (
    <section
      aria-labelledby={`allocation-${accountId}`}
      className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4"
    >
      <h2 id={`allocation-${accountId}`} className="text-ink-secondary text-sm">
        Allocation
      </h2>

      {allocation === null ? (
        <p className="text-ink-muted mt-2 text-sm">
          {failed ? "The allocation could not be loaded." : "Loading allocation…"}
        </p>
      ) : editing ? (
        <AllocationForm
          accountId={accountId}
          allocation={allocation}
          today={today}
          onSaved={(saved) => {
            setAllocation(saved);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <Current allocation={allocation} />
          {allocation.status !== "derived" ? (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="border-hairline hover:bg-surface-2 mt-3 rounded-lg border px-3 py-1.5 text-sm"
            >
              {allocation.status === "unknown" ? "Set allocation" : "Change allocation"}
            </button>
          ) : null}
          <History allocation={allocation} />
        </>
      )}
    </section>
  );
}

function Current({ allocation }: { allocation: Allocation }) {
  if (allocation.status === "unknown") {
    return (
      <p className="text-ink-secondary mt-2 text-sm">
        Unknown. Nothing is recorded, so the advisor will not guess what this account holds.
      </p>
    );
  }
  return (
    <div className="mt-2">
      <ul className="space-y-1 text-sm">
        {allocation.shares.map((share) => (
          <li key={share.asset_class} className="flex justify-between gap-4">
            <span>{ASSET_CLASS_LABELS[share.asset_class]}</span>
            <span className="tabular-nums">{formatBps(share.percentage_bps)}</span>
          </li>
        ))}
      </ul>
      {allocation.status === "derived" ? (
        <p className="text-ink-muted mt-1 text-xs">Follows from the account type.</p>
      ) : null}
    </div>
  );
}

function History({ allocation }: { allocation: Allocation }) {
  const rows = changes(allocation);
  if (rows.length === 0) return null;
  return (
    <div className="mt-4">
      <h3 className="text-ink-secondary text-xs">History</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {rows.map((row) => (
          <li key={row.from}>
            <span className="text-ink-secondary whitespace-nowrap">
              {rangeText(row.from, row.to)}
            </span>
            <span className="text-ink-muted"> · </span>
            {row.parts.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AllocationForm({
  accountId,
  allocation,
  today,
  onSaved,
  onCancel,
}: {
  accountId: number;
  allocation: Allocation;
  today: string;
  onSaved: (allocation: Allocation) => void;
  onCancel: () => void;
}) {
  const [percents, setPercents] = useState<Percents>(() => percentsFrom(allocation));
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const { shares, totalBps, problem } = readPercents(percents);
  const ready = problem === null && Boolean(effectiveFrom);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setSubmitting(true);
    setFailure(null);
    try {
      const saved = await apiFetch("/accounts/{account_id}/allocations", {
        method: "post",
        params: { account_id: accountId },
        body: { effective_from: effectiveFrom, shares },
      });
      onSaved(saved);
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The allocation was not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="mt-3 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-ink-secondary text-sm">Start from</span>
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => setPercents({ ...EMPTY, ...preset.percents })}
            className="border-hairline hover:bg-surface-2 rounded-full border px-3 py-1 text-xs"
          >
            {preset.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {CLASSES.map((assetClass) => (
          <Field key={assetClass} label={ASSET_CLASS_LABELS[assetClass]}>
            {({ id }) => (
              <div className="flex items-center gap-2">
                <input
                  id={id}
                  type="text"
                  inputMode="decimal"
                  value={percents[assetClass]}
                  placeholder="0"
                  onChange={(event) =>
                    setPercents((current) => ({ ...current, [assetClass]: event.target.value }))
                  }
                  className={`${inputClass} w-20 tabular-nums`}
                />
                <span className="text-ink-secondary text-sm">%</span>
              </div>
            )}
          </Field>
        ))}
      </div>

      <p
        aria-live="polite"
        className={`text-sm tabular-nums ${problem ? "text-critical-text" : "text-ink-secondary"}`}
      >
        {problem ?? `Total ${formatBps(totalBps)}`}
      </p>

      <Field label="From" hint="The previous allocation ends the day before.">
        {({ id, describedBy }) => (
          <input
            id={id}
            type="date"
            value={effectiveFrom}
            aria-describedby={describedBy}
            onChange={(event) => setEffectiveFrom(event.target.value)}
            className={`${inputClass} w-44`}
          />
        )}
      </Field>

      {failure ? (
        <p role="alert" className="text-critical-text text-sm">
          {failure}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!ready || submitting}
          className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save allocation"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
