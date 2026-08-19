"use client";

/**
 * Change an ownership stake.
 *
 * This is the form that has to *explain itself*, not just collect a percentage.
 * Effective-dating is the reason your past net worth does not silently rewrite itself
 * when your ownership changes, and it is completely invisible unless the form says so
 * — so it says so, in a sentence, and then shows the resulting history before you
 * commit to it.
 *
 * The preview is the point. "Changing this closes the current stake on 1 June and
 * opens a new one, and your net worth before that date will not move" is a claim the
 * reader can check against a table, which is what makes effective-dating
 * comprehensible instead of merely correct.
 */

import { useMemo, useState } from "react";

import { Field, FormActions, inputClass } from "@/components/forms/fields";
import { percentToBps } from "@/components/forms/account-form";
import { todayIso } from "@/components/forms/balance-form";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatBps, formatDate } from "@/lib/format";

type Stake = ResponseOf<"/accounts/{account_id}", "get">["stakes"][number];

export interface PreviewRow {
  ownerName: string;
  percentageBps: number;
  from: string;
  to: string | null;
  /** Marks the row this change would create, so the preview reads as a diff. */
  isNew: boolean;
}

/**
 * What the stake history becomes if this change is saved.
 *
 * Mirrors `transition_stake` in `services/ownership.py`: the open stake for that owner
 * closes at `effectiveFrom` and a new row opens there. Anything that already ended
 * before the change is untouched, which is exactly the property worth showing — it is
 * the visible form of "your past net worth will not move".
 */
export function previewStakes(
  stakes: Stake[],
  ownerUserId: number,
  ownerName: string,
  percentageBps: number,
  effectiveFrom: string,
): PreviewRow[] {
  const rows: PreviewRow[] = [];

  for (const stake of stakes) {
    const open = !stake.effective_to || stake.effective_to > effectiveFrom;
    if (stake.owner_user_id === ownerUserId && open) {
      // A change dated at or before a stake's own start replaces it rather than
      // closing it into a zero-length range.
      if (stake.effective_from >= effectiveFrom) continue;
      rows.push({
        ownerName: stake.owner_display_name,
        percentageBps: stake.percentage_bps,
        from: stake.effective_from,
        to: effectiveFrom,
        isNew: false,
      });
    } else {
      rows.push({
        ownerName: stake.owner_display_name,
        percentageBps: stake.percentage_bps,
        from: stake.effective_from,
        to: stake.effective_to ?? null,
        isNew: false,
      });
    }
  }

  rows.push({
    ownerName: ownerName,
    percentageBps,
    from: effectiveFrom,
    to: null,
    isNew: true,
  });

  return rows.sort((a, b) => a.from.localeCompare(b.from));
}

/** The half-open end bound as the last day it actually applied. */
export function lastDay(iso: string): string {
  const end = new Date(`${iso}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() - 1);
  return end.toISOString().slice(0, 10);
}

export function StakeForm({
  accountId,
  stakes,
  ownerUserId,
  ownerName,
  onSaved,
  onCancel,
}: {
  accountId: number;
  stakes: Stake[];
  ownerUserId: number;
  ownerName: string;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const current = stakes.find(
    (stake) => !stake.effective_to && stake.owner_user_id === ownerUserId,
  );
  const [percent, setPercent] = useState(() =>
    current ? String(current.percentage_bps / 100) : "100",
  );
  const [effectiveFrom, setEffectiveFrom] = useState(() => todayIso());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const bps = percentToBps(percent);
  const valid =
    percent.trim() !== "" && !Number.isNaN(Number(percent)) && bps >= 0 && bps <= 10_000;

  const preview = useMemo(
    () =>
      valid && effectiveFrom
        ? previewStakes(stakes, ownerUserId, ownerName, bps, effectiveFrom)
        : [],
    [valid, stakes, ownerUserId, ownerName, bps, effectiveFrom],
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) {
      setError("A stake must be between 0% and 100%.");
      return;
    }
    if (!effectiveFrom) {
      setError("Say what date the new stake starts.");
      return;
    }
    setError(null);
    setSubmitting(true);
    setFailure(null);
    try {
      await apiFetch("/accounts/{account_id}/stakes", {
        method: "post",
        params: { account_id: accountId },
        body: {
          owner_user_id: ownerUserId,
          percentage_bps: bps,
          effective_from: effectiveFrom,
        },
      });
      onSaved();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The stake was not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="New share" error={error}>
          {({ id, describedBy, invalid }) => (
            <div className="flex items-center gap-2">
              <input
                id={id}
                type="text"
                inputMode="decimal"
                value={percent}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                onChange={(event) => setPercent(event.target.value)}
                className={`${inputClass} w-24 tabular-nums`}
              />
              <span className="text-ink-secondary text-sm">%</span>
            </div>
          )}
        </Field>

        <Field label="Starting from">
          {({ id, describedBy }) => (
            <input
              id={id}
              type="date"
              value={effectiveFrom}
              aria-describedby={describedBy}
              onChange={(event) => setEffectiveFrom(event.target.value)}
              className={inputClass}
            />
          )}
        </Field>
      </div>

      {/* The sentence that makes effective-dating comprehensible rather than
          merely correct. */}
      <p className="text-ink-secondary mt-3 text-sm">
        {current ? (
          <>
            This closes your current {formatBps(current.percentage_bps)} stake on{" "}
            {effectiveFrom ? formatDate(effectiveFrom) : "the date you pick"} and opens a new one
            from that day.{" "}
            <strong className="font-medium">Your past net worth will not change</strong> — history
            is kept, not rewritten.
          </>
        ) : (
          <>
            This opens a stake from{" "}
            {effectiveFrom ? formatDate(effectiveFrom) : "the date you pick"}. Net worth before that
            date is unaffected.
          </>
        )}
      </p>

      {preview.length > 0 ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="text-ink-secondary py-2 text-left text-xs">
              Ownership history after this change
            </caption>
            <thead>
              <tr className="border-hairline text-ink-secondary border-b text-left">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Owner
                </th>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Share
                </th>
                <th scope="col" className="py-1.5 font-medium">
                  In effect
                </th>
              </tr>
            </thead>
            <tbody>
              {preview.map((row, index) => (
                <tr
                  key={`${row.ownerName}-${row.from}-${index}`}
                  className={`border-hairline/60 border-b last:border-0 ${
                    row.isNew ? "bg-accent-bg/40" : ""
                  }`}
                >
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                    {row.ownerName}
                    {row.isNew ? (
                      <span className="text-accent-strong ml-1.5 text-[10px] tracking-wide uppercase">
                        new
                      </span>
                    ) : null}
                  </th>
                  <td className="py-1.5 pr-3 tabular-nums">{formatBps(row.percentageBps)}</td>
                  <td className="text-ink-secondary py-1.5 whitespace-nowrap">
                    {formatDate(row.from)} — {row.to ? formatDate(lastDay(row.to)) : "now"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <FormActions
        submitting={submitting}
        error={failure}
        submitLabel="Save ownership change"
        onCancel={onCancel}
      />
    </form>
  );
}
