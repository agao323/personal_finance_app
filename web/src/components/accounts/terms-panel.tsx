"use client";

/**
 * A debt's terms, on the debt: the APR, what it costs to carry, and when they were last checked.
 *
 * The panel owns its own fetch and its own save. Saving puts the server's answer in place of
 * what was shown — the rate that applies today and the stale flag are the server's, not
 * guessed here — and nothing else on the page reloads.
 *
 * On the wire an APR is **thousandths of a percent** (6875 is 6.875%), because loan rates are
 * quoted to three decimals and basis points stop at two.
 */

import { useEffect, useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { StaleBadge } from "@/components/states";
import type { BodyOf, ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";

export type Terms = NonNullable<ResponseOf<"/accounts/{account_id}/terms", "get">>;
type TermsUpdate = BodyOf<"/accounts/{account_id}/terms", "put">;

/** 6875 → "6.875%". Always three decimals, as a lender quotes it. */
export function formatApr(thousandths: number): string {
  const whole = Math.trunc(thousandths / 1000);
  const fraction = String(thousandths % 1000).padStart(3, "0");
  return `${whole}.${fraction}%`;
}

/** "6.875" → 6875; null when it is not a rate from 0 to 100 with at most three decimals. */
export function parseApr(input: string): number | null {
  const text = input.trim().replace(/%$/, "");
  if (!/^\d{1,3}(\.\d{0,3})?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  const thousandths = Number(whole) * 1000 + Number(fraction.padEnd(3, "0"));
  return thousandths <= 100_000 ? thousandths : null;
}

function centsText(cents: number | null | undefined): string {
  return cents == null ? "" : (cents / 100).toFixed(2);
}

interface TermsValues {
  apr: string;
  minimumPayment: string;
  creditLimit: string;
  termMonths: string;
  maturityOn: string;
  promoApr: string;
  promoEndsOn: string;
  asOf: string;
}

type TermsErrors = Partial<Record<keyof TermsValues, string>>;

function valuesFrom(terms: Terms | null, today: string): TermsValues {
  return {
    apr: terms ? formatApr(terms.apr_pct_thousandths).replace("%", "") : "",
    minimumPayment: centsText(terms?.minimum_payment_cents),
    creditLimit: centsText(terms?.credit_limit_cents),
    termMonths: terms?.term_months == null ? "" : String(terms.term_months),
    maturityOn: terms?.maturity_on ?? "",
    promoApr:
      terms?.promo_apr_pct_thousandths == null
        ? ""
        : formatApr(terms.promo_apr_pct_thousandths).replace("%", ""),
    promoEndsOn: terms?.promo_ends_on ?? "",
    // Saving is checking: the date moves to today unless the form says otherwise.
    asOf: today,
  };
}

/** The body to save, or the errors that stop it. Pure, so every branch is testable. */
export function termsBody(
  values: TermsValues,
  money: { minimumPayment: number | null; creditLimit: number | null },
): { body: TermsUpdate } | { errors: TermsErrors } {
  const errors: TermsErrors = {};
  const apr = parseApr(values.apr);
  if (apr === null) errors.apr = "Enter the APR as a percent, like 6.875.";
  const promo = values.promoApr.trim() ? parseApr(values.promoApr) : null;
  if (values.promoApr.trim() && promo === null) errors.promoApr = "Enter a rate like 0 or 2.99.";
  if (values.promoApr.trim() && !values.promoEndsOn) {
    errors.promoEndsOn = "A promotional rate needs the date it ends.";
  }
  if (values.minimumPayment.trim() && money.minimumPayment === null) {
    errors.minimumPayment = "Enter an amount like 35.00.";
  }
  if (values.creditLimit.trim() && !money.creditLimit) {
    errors.creditLimit = "Enter a limit above zero.";
  }
  const months = values.termMonths.trim();
  if (months && !(/^\d+$/.test(months) && Number(months) > 0)) {
    errors.termMonths = "Enter a whole number of months.";
  }
  if (Object.keys(errors).length > 0) return { errors };

  return {
    body: {
      apr_pct_thousandths: apr as number,
      minimum_payment_cents: values.minimumPayment.trim() ? money.minimumPayment : null,
      credit_limit_cents: values.creditLimit.trim() ? money.creditLimit : null,
      term_months: months ? Number(months) : null,
      maturity_on: values.maturityOn || null,
      promo_apr_pct_thousandths: promo,
      promo_ends_on: promo === null ? null : values.promoEndsOn,
      as_of: values.asOf || null,
    },
  };
}

export function TermsPanel({
  accountId,
  isCard,
  today = new Date().toISOString().slice(0, 10),
}: {
  accountId: number;
  /** Cards have a credit limit; loans have a term and a maturity. */
  isCard: boolean;
  today?: string;
}) {
  // `undefined` is "nothing has arrived yet"; `null` is "arrived, and none are recorded".
  const [terms, setTerms] = useState<Terms | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts/{account_id}/terms", { params: { account_id: accountId } })
      .then((data) => {
        if (live) setTerms(data ?? null);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [accountId]);

  return (
    <section
      aria-labelledby={`terms-${accountId}`}
      className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4"
    >
      <h2 id={`terms-${accountId}`} className="text-ink-secondary text-sm">
        Terms
      </h2>

      {terms === undefined ? (
        <p className="text-ink-muted mt-2 text-sm">
          {failed ? "The terms could not be loaded." : "Loading terms…"}
        </p>
      ) : editing ? (
        <TermsForm
          accountId={accountId}
          isCard={isCard}
          terms={terms}
          today={today}
          onSaved={(saved) => {
            setTerms(saved);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          {terms ? (
            <TermsFigures terms={terms} isCard={isCard} />
          ) : (
            <p className="text-ink-secondary mt-2 text-sm">
              No terms recorded. Without an APR the advisor can say what this debt is, but not what
              it costs.
            </p>
          )}
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="border-hairline hover:bg-surface-2 mt-3 rounded-lg border px-3 py-1.5 text-sm"
          >
            {terms ? "Update terms" : "Record terms"}
          </button>
        </>
      )}
    </section>
  );
}

function TermsFigures({ terms, isCard }: { terms: Terms; isCard: boolean }) {
  const promoActive = terms.effective_apr_pct_thousandths !== terms.apr_pct_thousandths;
  const rows: [string, string][] = [["APR", formatApr(terms.apr_pct_thousandths)]];
  if (terms.promo_apr_pct_thousandths != null && terms.promo_ends_on) {
    rows.push([
      "Promotional rate",
      `${formatApr(terms.promo_apr_pct_thousandths)} ${promoActive ? "through" : "ended"} ${formatDate(terms.promo_ends_on)}`,
    ]);
  }
  if (terms.minimum_payment_cents != null) {
    rows.push(["Minimum payment", formatCurrency(terms.minimum_payment_cents)]);
  }
  if (isCard && terms.credit_limit_cents != null) {
    rows.push(["Credit limit", formatCurrency(terms.credit_limit_cents)]);
  }
  if (terms.term_months != null) rows.push(["Term", `${terms.term_months} months`]);
  if (terms.maturity_on) rows.push(["Matures", formatDate(terms.maturity_on)]);

  return (
    <div className="mt-2">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-ink-secondary">{label}</dt>
            <dd className="tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-ink-muted mt-2 flex flex-wrap items-center gap-2 text-xs">
        Checked on {formatDate(terms.as_of)}
        {terms.stale ? <StaleBadge asOf={terms.as_of} /> : null}
      </p>
      {terms.stale ? (
        <p className="text-ink-secondary mt-1 text-sm">
          More than a year old. Rates change; check the latest statement.
        </p>
      ) : null}
    </div>
  );
}

function TermsForm({
  accountId,
  isCard,
  terms,
  today,
  onSaved,
  onCancel,
}: {
  accountId: number;
  isCard: boolean;
  terms: Terms | null;
  today: string;
  onSaved: (terms: Terms) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState(() => valuesFrom(terms, today));
  const [money, setMoney] = useState(() => ({
    minimumPayment: terms?.minimum_payment_cents ?? null,
    creditLimit: terms?.credit_limit_cents ?? null,
  }));
  const [errors, setErrors] = useState<TermsErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  function update(patch: Partial<TermsValues>) {
    setValues((current) => ({ ...current, ...patch }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const outcome = termsBody(values, money);
    if ("errors" in outcome) {
      setErrors(outcome.errors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    setFailure(null);
    try {
      const saved = await apiFetch("/accounts/{account_id}/terms", {
        method: "put",
        params: { account_id: accountId },
        body: outcome.body,
      });
      onSaved(saved);
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The terms were not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  const percent = (key: "apr" | "promoApr", label: string, hint?: string) => (
    <Field label={label} error={errors[key]} hint={hint}>
      {({ id, describedBy, invalid }) => (
        <div className="flex items-center gap-2">
          <input
            id={id}
            type="text"
            inputMode="decimal"
            value={values[key]}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => update({ [key]: event.target.value })}
            className={`${inputClass} w-28 tabular-nums`}
          />
          <span className="text-ink-secondary text-sm">%</span>
        </div>
      )}
    </Field>
  );

  const date = (key: "maturityOn" | "promoEndsOn" | "asOf", label: string, hint?: string) => (
    <Field label={label} error={errors[key]} hint={hint}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          type="date"
          value={values[key]}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          onChange={(event) => update({ [key]: event.target.value })}
          className={inputClass}
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={submit} noValidate className="mt-3 space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {percent("apr", "APR", "As the statement quotes it, to three decimals.")}
        <Field label="Minimum payment" error={errors.minimumPayment}>
          {({ id, describedBy, invalid }) => (
            <MoneyInput
              id={id}
              value={values.minimumPayment}
              describedBy={describedBy}
              invalid={invalid}
              onChange={(raw, cents) => {
                update({ minimumPayment: raw });
                setMoney((current) => ({ ...current, minimumPayment: cents }));
              }}
            />
          )}
        </Field>
        {isCard ? (
          <Field label="Credit limit" error={errors.creditLimit}>
            {({ id, describedBy, invalid }) => (
              <MoneyInput
                id={id}
                value={values.creditLimit}
                describedBy={describedBy}
                invalid={invalid}
                onChange={(raw, cents) => {
                  update({ creditLimit: raw });
                  setMoney((current) => ({ ...current, creditLimit: cents }));
                }}
              />
            )}
          </Field>
        ) : (
          <>
            <Field label="Term in months" error={errors.termMonths}>
              {({ id, describedBy, invalid }) => (
                <input
                  id={id}
                  type="text"
                  inputMode="numeric"
                  value={values.termMonths}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  onChange={(event) => update({ termMonths: event.target.value })}
                  className={`${inputClass} w-28 tabular-nums`}
                />
              )}
            </Field>
            {date("maturityOn", "Matures on")}
          </>
        )}
        {percent("promoApr", "Promotional rate", "Optional. A 0% balance transfer, say.")}
        {date("promoEndsOn", "Promotion ends")}
        {date("asOf", "Checked on", "Terms older than a year are marked stale.")}
      </div>
      <FormActions
        submitting={submitting}
        error={failure}
        submitLabel="Save terms"
        onCancel={onCancel}
      />
    </form>
  );
}
