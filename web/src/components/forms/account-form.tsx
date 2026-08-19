"use client";

/**
 * Create or edit an account.
 *
 * Validation mirrors the API's rather than inventing its own: name 1–160 characters,
 * stake 0–100%, a balance date that is a real date. Where the two could drift the
 * server is still the authority — a rejected submit surfaces its message rather than
 * being swallowed, because a form that believes it validated everything is how a 422
 * becomes a silent no-op.
 *
 * The subtype list narrows by kind. That pairing is a UI affordance, not a rule the
 * API enforces: nothing server-side stops a mortgage being filed as a liquid asset,
 * and it is not worth a migration to prevent something a picker can simply not offer.
 */

import { useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { SUBTYPE_LABELS, type Account, type AccountKind } from "@/components/account-row";
import type { BodyOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";

type Subtype = Account["subtype"];

export const SUBTYPES_BY_KIND: Record<AccountKind, Subtype[]> = {
  liquid_asset: ["checking", "savings", "money_market", "cd", "brokerage"],
  illiquid_asset: [
    "ira",
    "roth_ira",
    "401k",
    "hsa",
    "529",
    "real_estate",
    "vehicle",
    "other_asset",
  ],
  liability: [
    "credit_card",
    "mortgage",
    "auto_loan",
    "student_loan",
    "personal_loan",
    "other_liability",
  ],
};

const KIND_OPTIONS: { value: AccountKind; label: string; hint: string }[] = [
  { value: "liquid_asset", label: "Liquid asset", hint: "Cash you could spend this week" },
  { value: "illiquid_asset", label: "Illiquid asset", hint: "Owned, but not quickly spendable" },
  { value: "liability", label: "Liability", hint: "Money you owe. Enter the balance positive" },
];

export interface AccountFormValues {
  name: string;
  kind: AccountKind;
  subtype: Subtype;
  institution: string;
  balance: string;
  balanceAsOf: string;
  stakePercent: string;
}

export function emptyAccountForm(today = new Date()): AccountFormValues {
  return {
    name: "",
    kind: "liquid_asset",
    subtype: "checking",
    institution: "",
    balance: "",
    balanceAsOf: today.toISOString().slice(0, 10),
    stakePercent: "100",
  };
}

export type AccountFormErrors = Partial<Record<keyof AccountFormValues, string>>;

/**
 * Client-side validation, mirroring the API's constraints.
 *
 * Exported and pure so every branch is testable without rendering a form and driving
 * it — there are more failure paths here than a component test can comfortably reach.
 */
export function validateAccount(
  values: AccountFormValues,
  cents: number | null,
): AccountFormErrors {
  const errors: AccountFormErrors = {};

  const name = values.name.trim();
  if (name.length === 0) errors.name = "Give the account a name.";
  else if (name.length > 160) errors.name = "Names are limited to 160 characters.";

  if (!SUBTYPES_BY_KIND[values.kind].includes(values.subtype)) {
    errors.subtype = "Pick a type that matches the kind of account.";
  }

  // An opening balance is optional, but half of one is not: a figure with no date
  // would be recorded against today, which is a claim nobody made.
  if (values.balance.trim() !== "") {
    if (cents === null) errors.balance = "Enter an amount like 1234.56.";
    else if (!values.balanceAsOf) errors.balanceAsOf = "Say what date this balance is from.";
  }

  const percent = Number(values.stakePercent);
  if (!values.stakePercent.trim() || Number.isNaN(percent)) {
    errors.stakePercent = "Enter a percentage between 0 and 100.";
  } else if (percent < 0 || percent > 100) {
    errors.stakePercent = "A stake cannot be less than 0% or more than 100%.";
  }

  return errors;
}

/** Percent as typed → basis points. `33.33` is 3333, not 3332.9999. */
export function percentToBps(percent: string): number {
  const [whole = "0", fraction = ""] = percent.trim().split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

export function AccountForm({
  onCreated,
  onCancel,
}: {
  onCreated: (account: { id: number; name: string }) => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<AccountFormValues>(() => emptyAccountForm());
  const [cents, setCents] = useState<number | null>(null);
  const [errors, setErrors] = useState<AccountFormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function update(patch: Partial<AccountFormValues>) {
    setValues((current) => {
      const next = { ...current, ...patch };
      // Changing the kind strands a subtype that no longer belongs to it.
      if (patch.kind && !SUBTYPES_BY_KIND[patch.kind].includes(next.subtype)) {
        next.subtype = SUBTYPES_BY_KIND[patch.kind][0];
      }
      return next;
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validateAccount(values, cents);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const body: BodyOf<"/accounts", "post"> = {
      name: values.name.trim(),
      kind: values.kind,
      subtype: values.subtype,
      ownership_percentage_bps: percentToBps(values.stakePercent),
      ...(values.institution.trim() ? { institution_name: values.institution.trim() } : {}),
      ...(values.balance.trim() && cents !== null
        ? { opening_balance_cents: cents, opening_balance_as_of: values.balanceAsOf }
        : {}),
    };

    setSubmitting(true);
    setFailure(null);
    try {
      const account = await apiFetch("/accounts", { method: "post", body });
      onCreated({ id: account.id, name: account.name });
    } catch (cause: unknown) {
      // The server is the authority. Its message says what this form missed.
      setFailure(cause instanceof Error ? cause.message : "The account was not created.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Field label="Name" error={errors.name}>
        {({ id, describedBy, invalid }) => (
          <input
            id={id}
            type="text"
            value={values.name}
            placeholder="Everyday checking"
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => update({ name: event.target.value })}
            className={inputClass}
          />
        )}
      </Field>

      <Field label="Kind" hint={KIND_OPTIONS.find((option) => option.value === values.kind)?.hint}>
        {({ id, describedBy }) => (
          <select
            id={id}
            value={values.kind}
            aria-describedby={describedBy}
            onChange={(event) => update({ kind: event.target.value as AccountKind })}
            className={inputClass}
          >
            {KIND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
      </Field>

      <Field label="Type" error={errors.subtype}>
        {({ id, describedBy, invalid }) => (
          <select
            id={id}
            value={values.subtype}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => update({ subtype: event.target.value as Subtype })}
            className={inputClass}
          >
            {SUBTYPES_BY_KIND[values.kind].map((subtype) => (
              <option key={subtype} value={subtype}>
                {SUBTYPE_LABELS[subtype]}
              </option>
            ))}
          </select>
        )}
      </Field>

      <Field label="Institution" hint="Optional. Reused if you have used the name before.">
        {({ id, describedBy }) => (
          <input
            id={id}
            type="text"
            value={values.institution}
            placeholder="Meridian Bank"
            aria-describedby={describedBy}
            onChange={(event) => update({ institution: event.target.value })}
            className={inputClass}
          />
        )}
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Opening balance"
          error={errors.balance}
          hint={
            values.kind === "liability" ? "Enter what you owe as a positive number." : undefined
          }
        >
          {({ id, describedBy, invalid }) => (
            <MoneyInput
              id={id}
              value={values.balance}
              describedBy={describedBy}
              invalid={invalid}
              onChange={(raw, parsed) => {
                update({ balance: raw });
                setCents(parsed);
              }}
            />
          )}
        </Field>

        <Field label="As of" error={errors.balanceAsOf}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="date"
              value={values.balanceAsOf}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              onChange={(event) => update({ balanceAsOf: event.target.value })}
              className={inputClass}
            />
          )}
        </Field>
      </div>

      <Field
        label="Your ownership"
        error={errors.stakePercent}
        hint="What share of this account counts toward your net worth. Change it later from the account page."
      >
        {({ id, describedBy, invalid }) => (
          <div className="flex items-center gap-2">
            <input
              id={id}
              type="text"
              inputMode="decimal"
              value={values.stakePercent}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              onChange={(event) => update({ stakePercent: event.target.value })}
              className={`${inputClass} w-24 tabular-nums`}
            />
            <span className="text-ink-secondary text-sm">%</span>
          </div>
        )}
      </Field>

      <FormActions
        submitting={submitting}
        error={failure}
        submitLabel="Create account"
        onCancel={onCancel}
      />
    </form>
  );
}
