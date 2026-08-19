"use client";

/**
 * The categorisation rule set.
 *
 * PRODUCT.md commits to a user-editable rule set in v1, and editable by `curl` is not
 * that. This is what keeps the spend numbers trustworthy over time: uncategorised
 * spending shows up on the spending screen, gets fixed on the transactions screen, and
 * a rule written here stops it coming back.
 *
 * The note about manual categorisations is permanent, not a toast. "Re-running is
 * safe" is the property that makes anyone willing to press the button, and it is
 * invisible in the UI otherwise.
 */

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import type { Category } from "@/components/category-picker";
import { RuleForm, type Rule } from "@/components/rules/rule-form";
import { RuleList, inRunOrder, swapTarget } from "@/components/rules/rule-list";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";

export default function RulesPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <RulesScreen />
    </Suspense>
  );
}

export function RulesScreen() {
  const search = useSearchParams();
  // The spending and transactions screens link here with ?pattern=<merchant>, so
  // "this keeps coming up uncategorised" turns into a rule without retyping it.
  const prefill = search?.get("pattern") ?? "";

  const [rules, setRules] = useState<Rule[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [creating, setCreating] = useState(prefill !== "");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState<{
    examined: number;
    categorised: number;
    manual_preserved: number;
  } | null>(null);

  // A counter rather than an imperative `load()`: calling an async loader from the
  // effect body reads as a synchronous setState to React's lint rule, and bumping a
  // dependency is the shape the rest of this app already uses to refetch.
  const [revision, setRevision] = useState(0);
  const reload = () => setRevision((current) => current + 1);

  useEffect(() => {
    let live = true;
    apiFetch("/rules")
      .then((next) => {
        if (!live) return;
        setRules(next);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!live) return;
        setRules(null);
        setError(cause instanceof Error ? cause.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, [revision]);

  useEffect(() => {
    let live = true;
    apiFetch("/categories")
      .then((next) => {
        if (live) setCategories(next);
      })
      .catch(() => {
        if (live) setCategories([]);
      });
    return () => {
      live = false;
    };
  }, []);

  async function move(rule: Rule, direction: "up" | "down") {
    const target = swapTarget(inRunOrder(rules ?? []), rule.id, direction);
    if (!target) return;
    setBusyId(rule.id);
    try {
      // Swap the two priorities. Renumbering the whole list would be one write per
      // rule and would churn every priority to move one.
      await apiFetch("/rules/{rule_id}", {
        method: "patch",
        params: { rule_id: target.rule.id },
        body: { priority: target.other.priority },
      });
      await apiFetch("/rules/{rule_id}", {
        method: "patch",
        params: { rule_id: target.other.id },
        body: { priority: target.rule.priority },
      });
      reload();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The rules were not reordered.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(rule: Rule) {
    setBusyId(rule.id);
    try {
      await apiFetch("/rules/{rule_id}", { method: "delete", params: { rule_id: rule.id } });
      reload();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The rule was not deleted.");
    } finally {
      setBusyId(null);
    }
  }

  async function applyAll() {
    setApplying(true);
    setApplied(null);
    try {
      setApplied(await apiFetch("/rules/apply", { method: "post", body: {} }));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The rules did not run.");
    } finally {
      setApplying(false);
    }
  }

  const showForm = creating || editing !== null;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-medium tracking-tight">Rules</h1>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={applyAll}
            disabled={applying || rules === null || rules.length === 0}
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
          >
            {applying ? "Running…" : "Run all rules"}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setCreating(true);
            }}
            className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            New rule
          </button>
        </div>
      </div>

      <p className="text-ink-secondary mt-2 text-sm">
        Rules run in order and the first match wins. Anything you categorised by hand is never
        overwritten, so running them again is always safe.
      </p>

      {applied ? (
        <div
          role="status"
          className="border-hairline bg-surface-1 mt-3 rounded-xl border p-3 text-sm"
        >
          Examined {applied.examined} transactions and changed{" "}
          <span className="font-medium">{applied.categorised}</span>.{" "}
          {applied.manual_preserved > 0
            ? `${applied.manual_preserved} were left alone because you had categorised them yourself.`
            : "Nothing was overwritten."}
        </div>
      ) : null}

      {error ? (
        <div className="mt-3">
          <ErrorState title="Rules problem" detail={error} onRetry={reload} />
        </div>
      ) : null}

      {showForm ? (
        <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
          <h2 className="mb-3 text-sm font-medium">{editing ? "Edit rule" : "New rule"}</h2>
          <RuleForm
            rule={editing}
            initialPattern={editing ? undefined : prefill}
            categories={categories}
            onSaved={() => {
              setEditing(null);
              setCreating(false);
              reload();
            }}
            onCancel={() => {
              setEditing(null);
              setCreating(false);
            }}
          />
        </div>
      ) : null}

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        {rules === null && !error ? (
          <Skeleton className="h-32 w-full" />
        ) : rules && rules.length === 0 ? (
          <EmptyState
            title="No rules yet"
            detail="A rule matches a merchant and applies a category, so the same purchase categorises itself every month."
          />
        ) : rules ? (
          <RuleList
            rules={rules}
            busyId={busyId}
            onEdit={(rule) => {
              setCreating(false);
              setEditing(rule);
            }}
            onDelete={remove}
            onMove={move}
          />
        ) : null}
      </div>
    </div>
  );
}
