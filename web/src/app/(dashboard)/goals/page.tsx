"use client";

/**
 * Goals: what the household is aiming for, and how each stands.
 *
 * **One goal changes, one row changes.** Adding a goal puts it at the top; saving or archiving
 * one replaces that row. Nothing reloads the list, and once it has loaded it never collapses to
 * a skeleton — the owner uses this on a phone, one goal at a time.
 */

import { useEffect, useState } from "react";

import { GoalForm, type AccountOption, type CategoryOption } from "@/components/goals/goal-form";
import { GoalRow } from "@/components/goals/goal-row";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import type { Goal, GoalCreate } from "@/lib/goals";

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([apiFetch("/goals"), apiFetch("/categories"), apiFetch("/accounts")])
      .then(([loadedGoals, loadedCategories, loadedAccounts]) => {
        if (!live) return;
        setGoals(loadedGoals);
        setCategories(
          loadedCategories
            .filter((category) => category.kind === "expense")
            .map((category) => ({ id: category.id, name: category.name })),
        );
        setAccounts(
          loadedAccounts.groups
            .flatMap((group) => group.accounts)
            .filter((account) => account.closed_at === null && account.kind !== "liability")
            .map((account) => ({ id: account.id, name: account.name })),
        );
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, []);

  async function create(body: GoalCreate) {
    const created = await apiFetch("/goals", { method: "post", body });
    setGoals((list) => [created, ...(list ?? [])]);
    setAdding(false);
  }

  function saved(goal: Goal) {
    setGoals((list) => (list ?? []).map((existing) => (existing.id === goal.id ? goal : existing)));
  }

  if (goals === null) {
    if (error) return <ErrorState title="Goals unavailable" detail={error} />;
    return <Skeleton className="h-64 w-full" />;
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-medium tracking-tight">Goals</h1>
        {adding ? null : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            Add a goal
          </button>
        )}
      </div>

      {adding ? (
        <section
          aria-label="Add a goal"
          className="border-hairline bg-surface-1 rounded-xl border p-4"
        >
          <GoalForm
            categories={categories}
            accounts={accounts}
            onCreate={create}
            onCancel={() => setAdding(false)}
          />
        </section>
      ) : null}

      {goals.length === 0 ? (
        <EmptyState
          title="No goals yet"
          detail="A spending limit on a category, an emergency fund in months, or a savings target by a date."
        />
      ) : (
        <ul aria-label="Goals" className="divide-hairline divide-y">
          {goals.map((goal) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              categories={categories}
              accounts={accounts}
              onSaved={saved}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
