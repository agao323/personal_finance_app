"use client";

/**
 * Add or edit a goal. Each kind asks for its own fields and nothing else, and says what is
 * missing before anything is sent — the API would refuse the same things, less helpfully.
 *
 * The kind and whose goal it is are chosen when adding; an edit keeps both, because they
 * define what the goal is.
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { ViewToggle, type ViewScope } from "@/components/view-toggle";
import { centsToInputValue } from "@/lib/format";
import {
  KIND_LABELS,
  parseMonthsToTenths,
  type Goal,
  type GoalCreate,
  type GoalKind,
  type GoalUpdate,
} from "@/lib/goals";

export type CategoryOption = { id: number; name: string };
export type AccountOption = { id: number; name: string };

/** `45` → `"4.5"`, `60` → `"6"`: the months field as a person would type it. */
function tenthsToInput(tenths: number): string {
  const rest = tenths % 10;
  return rest ? `${Math.trunc(tenths / 10)}.${rest}` : String(tenths / 10);
}

type Errors = Partial<Record<"name" | "category" | "amount" | "months" | "accounts", string>>;

export function GoalForm({
  goal,
  categories,
  accounts,
  onCreate,
  onUpdate,
  onCancel,
}: {
  goal?: Goal;
  categories: CategoryOption[];
  accounts: AccountOption[];
  onCreate?: (body: GoalCreate) => Promise<void>;
  onUpdate?: (body: GoalUpdate) => Promise<void>;
  onCancel?: () => void;
}) {
  const [kind, setKind] = useState<GoalKind>(goal?.kind ?? "spending_limit");
  const [view, setView] = useState<ViewScope>(goal?.view ?? "household");
  const [name, setName] = useState(goal?.name ?? "");
  const [categoryId, setCategoryId] = useState<number | null>(goal?.category_id ?? null);
  const [amountRaw, setAmountRaw] = useState(
    goal?.target_amount_cents ? centsToInputValue(goal.target_amount_cents) : "",
  );
  const [amountCents, setAmountCents] = useState<number | null>(goal?.target_amount_cents ?? null);
  const [monthsRaw, setMonthsRaw] = useState(
    goal?.target_months_tenths ? tenthsToInput(goal.target_months_tenths) : "",
  );
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [accountIds, setAccountIds] = useState<number[]>(goal?.account_ids ?? []);
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function validate(): Errors {
    const found: Errors = {};
    if (!name.trim()) found.name = "Give the goal a name.";
    if (kind === "spending_limit" && categoryId === null) found.category = "Choose a category.";
    if (kind !== "emergency_fund" && !(amountCents && amountCents > 0)) {
      found.amount =
        kind === "spending_limit" ? "Enter a monthly amount." : "Enter the amount to save.";
    }
    if (kind === "emergency_fund") {
      const tenths = parseMonthsToTenths(monthsRaw);
      if (!tenths) found.months = "Enter a number of months, like 6 or 4.5.";
    }
    if (kind === "savings_target" && accountIds.length === 0) {
      found.accounts = "Choose at least one account that counts toward it.";
    }
    return found;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const months = kind === "emergency_fund" ? parseMonthsToTenths(monthsRaw) : null;
    const amount = kind === "emergency_fund" ? null : amountCents;
    setSubmitting(true);
    setError(null);
    try {
      if (goal && onUpdate) {
        await onUpdate({
          name: name.trim(),
          ...(kind === "spending_limit" ? { category_id: categoryId } : {}),
          ...(amount !== null ? { target_amount_cents: amount } : {}),
          ...(months !== null ? { target_months_tenths: months } : {}),
          ...(kind === "savings_target"
            ? { target_date: targetDate || null, account_ids: accountIds }
            : {}),
        });
      } else if (onCreate) {
        await onCreate({
          kind,
          name: name.trim(),
          view,
          category_id: kind === "spending_limit" ? categoryId : null,
          target_amount_cents: amount,
          target_months_tenths: months,
          target_date: kind === "savings_target" && targetDate ? targetDate : null,
          account_ids: kind === "savings_target" ? accountIds : [],
        });
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-3">
      {goal ? null : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="text-ink-secondary text-sm" htmlFor="goal-kind">
            Kind
          </label>
          <select
            id="goal-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as GoalKind)}
            className={`${inputClass} w-auto`}
          >
            {(Object.keys(KIND_LABELS) as GoalKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
          <ViewToggle view={view} onChange={setView} />
        </div>
      )}

      <Field label="Name" error={errors.name}>
        {({ id, describedBy, invalid }) => (
          <input
            id={id}
            value={name}
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            className={inputClass}
          />
        )}
      </Field>

      {kind === "spending_limit" ? (
        <Field label="Category" error={errors.category}>
          {({ id, describedBy, invalid }) => (
            <select
              id={id}
              value={categoryId ?? ""}
              onChange={(event) =>
                setCategoryId(event.target.value ? Number(event.target.value) : null)
              }
              aria-describedby={describedBy}
              aria-invalid={invalid}
              className={inputClass}
            >
              <option value="">Choose…</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          )}
        </Field>
      ) : null}

      {kind === "emergency_fund" ? (
        <Field label="Months of spending" error={errors.months}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              inputMode="decimal"
              value={monthsRaw}
              onChange={(event) => setMonthsRaw(event.target.value)}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              className={inputClass}
              placeholder="6"
            />
          )}
        </Field>
      ) : (
        <Field
          label={kind === "spending_limit" ? "Monthly limit" : "Amount to save"}
          error={errors.amount}
        >
          {({ id, describedBy, invalid }) => (
            <MoneyInput
              id={id}
              value={amountRaw}
              describedBy={describedBy}
              invalid={invalid}
              onChange={(raw, cents) => {
                setAmountRaw(raw);
                setAmountCents(cents);
              }}
            />
          )}
        </Field>
      )}

      {kind === "savings_target" ? (
        <>
          <Field label="By (optional)">
            {({ id }) => (
              <input
                id={id}
                type="date"
                value={targetDate}
                onChange={(event) => setTargetDate(event.target.value)}
                className={inputClass}
              />
            )}
          </Field>
          <fieldset>
            <legend className="text-ink-secondary mb-1 text-sm">Accounts that count</legend>
            <div className="flex flex-col gap-1">
              {accounts.map((account) => (
                <label key={account.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={accountIds.includes(account.id)}
                    onChange={(event) =>
                      setAccountIds((ids) =>
                        event.target.checked
                          ? [...ids, account.id]
                          : ids.filter((existing) => existing !== account.id),
                      )
                    }
                  />
                  {account.name}
                </label>
              ))}
            </div>
            {errors.accounts ? (
              <p className="text-critical-text mt-1 text-xs">{errors.accounts}</p>
            ) : null}
          </fieldset>
        </>
      ) : null}

      <FormActions
        submitting={submitting}
        error={error}
        submitLabel={goal ? "Save goal" : "Add goal"}
        onCancel={onCancel}
      />
    </form>
  );
}
