"use client";

/**
 * One goal: what it aims for, how it stands, and — on the row itself — Edit and Archive.
 *
 * Progress is the server's (ticket 111). Until it has been computed the row says so plainly
 * rather than drawing an empty bar, which would read as "no progress at all".
 */

import Link from "next/link";
import { useState } from "react";

import { GoalForm, type AccountOption, type CategoryOption } from "@/components/goals/goal-form";
import { apiFetch } from "@/lib/api";
import { formatBps, formatCurrency } from "@/lib/format";
import {
  KIND_LABELS,
  describeTarget,
  formatMonthsTenths,
  type Goal,
  type GoalUpdate,
} from "@/lib/goals";

type Progress = NonNullable<Goal["progress"]>;

function ProgressFigures({ goal, progress }: { goal: Goal; progress: Progress }) {
  if (goal.kind === "spending_limit") {
    return (
      <p className="text-ink-secondary text-xs tabular-nums">
        {formatCurrency(progress.month_to_date_cents ?? 0)} spent this month of{" "}
        {formatCurrency(goal.target_amount_cents ?? 0)}
        {progress.last_month_cents != null
          ? ` · last month ${formatCurrency(progress.last_month_cents)}`
          : ""}
      </p>
    );
  }
  if (goal.kind === "emergency_fund") {
    return (
      <p className="text-ink-secondary text-xs tabular-nums">
        Cash covers {formatMonthsTenths(progress.runway_months_tenths ?? 0)} of{" "}
        {formatMonthsTenths(goal.target_months_tenths ?? 0)}
      </p>
    );
  }
  return (
    <p className="text-ink-secondary text-xs tabular-nums">
      {formatCurrency(progress.saved_cents ?? 0)} saved of{" "}
      {formatCurrency(goal.target_amount_cents ?? 0)}
      {progress.monthly_needed_cents != null
        ? ` · ${formatCurrency(progress.monthly_needed_cents)} a month to get there`
        : ""}
    </p>
  );
}

function ProgressBar({ bps, over }: { bps: number; over: boolean }) {
  const width = `${Math.min(100, Math.max(0, bps / 100))}%`;
  return (
    <span
      role="meter"
      aria-label="Progress"
      aria-valuenow={bps / 100}
      aria-valuemin={0}
      aria-valuemax={100}
      className="bg-hairline/60 mt-1 block h-1.5 w-full overflow-hidden rounded-full"
    >
      <span
        className={`block h-full rounded-full ${over ? "bg-critical" : "bg-series-1"}`}
        style={{ width }}
      />
    </span>
  );
}

export function GoalRow({
  goal,
  categories,
  accounts,
  onSaved,
}: {
  goal: Goal;
  categories: CategoryOption[];
  accounts: AccountOption[];
  onSaved: (goal: Goal) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const names = new Map(accounts.map((a) => [a.id, a.name]));
  const progress = goal.progress ?? null;
  const archived = goal.status === "archived";

  async function update(body: GoalUpdate) {
    const saved = await apiFetch("/goals/{goal_id}", {
      method: "patch",
      params: { goal_id: goal.id },
      body,
    });
    onSaved(saved);
    setEditing(false);
  }

  async function setStatus(status: "archived" | "active") {
    setError(null);
    try {
      await update({ status });
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Not saved.");
    }
  }

  return (
    <li className={`py-3 ${archived ? "opacity-60" : ""}`} aria-label={goal.name}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-ink text-sm font-medium">{goal.name}</p>
          <p className="text-ink-muted text-xs">
            {KIND_LABELS[goal.kind]} · {goal.view === "mine" ? "Mine" : "Household"}
            {archived ? " · archived" : goal.status === "achieved" ? " · achieved" : ""}
          </p>
          <p className="text-ink-secondary mt-1 text-sm">{describeTarget(goal, names)}</p>
          {goal.kind === "spending_limit" && goal.category_id ? (
            <Link
              href={`/spending?category=${goal.category_id}`}
              className="text-accent-strong text-xs hover:underline"
            >
              See {goal.category_name} on Spending
            </Link>
          ) : null}

          {progress ? (
            <div className="mt-2">
              {progress.progress_bps != null ? (
                <ProgressBar
                  bps={progress.progress_bps}
                  over={goal.kind === "spending_limit" && progress.progress_bps > 10000}
                />
              ) : null}
              <ProgressFigures goal={goal} progress={progress} />
              <p className="text-xs">
                <span className={progress.on_track ? "text-ink-secondary" : "text-warning-text"}>
                  {progress.on_track ? "On track" : "Off track"}
                </span>
                {progress.progress_bps != null ? (
                  <span className="text-ink-muted"> · {formatBps(progress.progress_bps)}</span>
                ) : null}
                {progress.stale ? (
                  <span className="bg-warning-bg text-warning-text ml-1 rounded px-1">Stale</span>
                ) : null}
              </p>
            </div>
          ) : (
            <p className="text-ink-muted mt-2 text-xs">Progress not yet computed.</p>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1 text-xs">
          <button
            type="button"
            onClick={() => setEditing((open) => !open)}
            aria-expanded={editing}
            className="text-ink-secondary hover:text-ink underline underline-offset-4"
          >
            {editing ? "Close" : "Edit"}
          </button>
          <button
            type="button"
            onClick={() => void setStatus(archived ? "active" : "archived")}
            className="text-ink-secondary hover:text-ink underline underline-offset-4"
          >
            {archived ? "Restore" : "Archive"}
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="text-critical-text mt-1 text-xs">
          {error}
        </p>
      ) : null}
      {editing ? (
        <div className="border-hairline mt-3 rounded-lg border p-3">
          <GoalForm
            goal={goal}
            categories={categories}
            accounts={accounts}
            onUpdate={update}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : null}
    </li>
  );
}
