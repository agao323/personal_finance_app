"use client";

/**
 * Planning: your birth year and retirement year, and the assumptions advice rests on.
 *
 * - **Your profile is yours.** The API has no member id to point at anyone else's.
 * - **Assumptions are versions, not settings.** Saving adds a new version on top; the old ones
 *   stay, listed beneath, because a projection records the version it used. The first version
 *   is the app's defaults, and says so — so does the advisor when it quotes them.
 * - **The mix must total 100%** before it can be saved; the running total says how far off it is.
 */

import { useEffect, useState } from "react";

import { Field, FormActions, MoneyInput, inputClass } from "@/components/forms/fields";
import { ErrorState, Skeleton } from "@/components/states";
import { apiFetch, type ResponseOf } from "@/lib/api";
import { centsToInputValue, formatBps, formatCurrency, formatDate } from "@/lib/format";
import {
  MIX_FIELDS,
  bpsToInput,
  mixTotal,
  parsePercentToBps,
  type Assumptions,
  type AssumptionsCreate,
  type MixField,
  type RiskTolerance,
} from "@/lib/planning";

type Profile = ResponseOf<"/planning/profile", "get">;

const RATE_FIELDS = [
  ["expected_real_return_bps", "Expected return after inflation"],
  ["inflation_bps", "Inflation"],
  ["withdrawal_low_bps", "Withdrawal rate, low"],
  ["withdrawal_high_bps", "Withdrawal rate, high"],
  ["tax_deferred_withdrawal_tax_bps", "Tax on tax-deferred withdrawals (flat)"],
] as const;
type RateField = (typeof RATE_FIELDS)[number][0];

const RISK: RiskTolerance[] = ["conservative", "moderate", "aggressive"];

function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const [birth, setBirth] = useState(profile.birth_year ? String(profile.birth_year) : "");
  const [retire, setRetire] = useState(
    profile.target_retirement_year ? String(profile.target_retirement_year) : "",
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const birthYear = birth.trim() ? Number(birth) : null;
    const retireYear = retire.trim() ? Number(retire) : null;
    if (
      (birthYear !== null && !Number.isInteger(birthYear)) ||
      (retireYear !== null && !Number.isInteger(retireYear))
    ) {
      setError("Years are whole numbers, like 1988.");
      return;
    }
    if (birthYear !== null && retireYear !== null && retireYear <= birthYear) {
      setError("The retirement year comes after the birth year.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const next = await apiFetch("/planning/profile", {
        method: "put",
        body: { birth_year: birthYear, target_retirement_year: retireYear },
      });
      onSaved(next);
      setSaved(true);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="grid gap-3 sm:grid-cols-2">
      <Field label="Birth year" hint="The year only — nothing finer is needed.">
        {({ id, describedBy }) => (
          <input
            id={id}
            inputMode="numeric"
            value={birth}
            onChange={(event) => setBirth(event.target.value)}
            aria-describedby={describedBy}
            className={inputClass}
          />
        )}
      </Field>
      <Field label="Target retirement year">
        {({ id }) => (
          <input
            id={id}
            inputMode="numeric"
            value={retire}
            onChange={(event) => setRetire(event.target.value)}
            className={inputClass}
          />
        )}
      </Field>
      <div className="sm:col-span-2">
        <FormActions submitting={submitting} error={error} submitLabel="Save profile" />
        {saved && !error ? <p className="text-ink-muted mt-1 text-xs">Saved.</p> : null}
      </div>
    </form>
  );
}

function initialValues(current: Assumptions) {
  const rates = Object.fromEntries(
    RATE_FIELDS.map(([field]) => [field, bpsToInput(current[field])]),
  ) as Record<RateField, string>;
  const mix = Object.fromEntries(
    MIX_FIELDS.map(([field]) => [field, bpsToInput(current[field])]),
  ) as Record<MixField, string>;
  return { rates, mix };
}

function AssumptionsForm({
  current,
  onSaved,
  onCancel,
}: {
  current: Assumptions;
  onSaved: (a: Assumptions) => void;
  onCancel: () => void;
}) {
  const start = initialValues(current);
  const [rates, setRates] = useState(start.rates);
  const [mix, setMix] = useState(start.mix);
  const [risk, setRisk] = useState<RiskTolerance>(current.risk_tolerance);
  const [healthRaw, setHealthRaw] = useState(
    current.pre65_healthcare_annual_cents != null
      ? centsToInputValue(current.pre65_healthcare_annual_cents)
      : "",
  );
  const [healthCents, setHealthCents] = useState<number | null>(
    current.pre65_healthcare_annual_cents ?? null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const total = mixTotal(mix);
  const mixOk = total === 10000;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = Object.fromEntries(
      RATE_FIELDS.map(([field]) => [field, parsePercentToBps(rates[field])]),
    ) as Record<RateField, number | null>;
    const bad = RATE_FIELDS.find(([field]) => parsed[field] === null);
    if (bad) {
      setError(`${bad[1]}: enter a percentage, like 4.5.`);
      return;
    }
    if (!mixOk) {
      setError("The target mix must total 100% before it can be saved.");
      return;
    }
    if (healthRaw.trim() && healthCents === null) {
      setError("Healthcare: enter an amount, or leave it empty.");
      return;
    }
    const body: AssumptionsCreate = {
      expected_real_return_bps: parsed.expected_real_return_bps as number,
      inflation_bps: parsed.inflation_bps as number,
      withdrawal_low_bps: parsed.withdrawal_low_bps as number,
      withdrawal_high_bps: parsed.withdrawal_high_bps as number,
      tax_deferred_withdrawal_tax_bps: parsed.tax_deferred_withdrawal_tax_bps as number,
      pre65_healthcare_annual_cents: healthRaw.trim() ? healthCents : null,
      risk_tolerance: risk,
      target_us_equity_bps: parsePercentToBps(mix.target_us_equity_bps) as number,
      target_intl_equity_bps: parsePercentToBps(mix.target_intl_equity_bps) as number,
      target_bonds_bps: parsePercentToBps(mix.target_bonds_bps) as number,
      target_cash_bps: parsePercentToBps(mix.target_cash_bps) as number,
      target_other_bps: parsePercentToBps(mix.target_other_bps) as number,
    };
    setSubmitting(true);
    setError(null);
    try {
      onSaved(await apiFetch("/planning/assumptions", { method: "post", body }));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {RATE_FIELDS.map(([field, label]) => (
          <Field key={field} label={`${label} (%)`}>
            {({ id }) => (
              <input
                id={id}
                inputMode="decimal"
                value={rates[field]}
                onChange={(event) => setRates((r) => ({ ...r, [field]: event.target.value }))}
                className={inputClass}
              />
            )}
          </Field>
        ))}
        <Field label="Healthcare a year before 65 (optional)">
          {({ id }) => (
            <MoneyInput
              id={id}
              value={healthRaw}
              onChange={(raw, cents) => {
                setHealthRaw(raw);
                setHealthCents(cents);
              }}
            />
          )}
        </Field>
        <Field label="Risk tolerance">
          {({ id }) => (
            <select
              id={id}
              value={risk}
              onChange={(event) => setRisk(event.target.value as RiskTolerance)}
              className={inputClass}
            >
              {RISK.map((level) => (
                <option key={level} value={level}>
                  {level[0].toUpperCase() + level.slice(1)}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>

      <fieldset>
        <legend className="text-ink-secondary mb-1 text-sm">Target mix (%)</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {MIX_FIELDS.map(([field, label]) => (
            <Field key={field} label={label}>
              {({ id }) => (
                <input
                  id={id}
                  inputMode="decimal"
                  value={mix[field]}
                  onChange={(event) => setMix((m) => ({ ...m, [field]: event.target.value }))}
                  className={inputClass}
                />
              )}
            </Field>
          ))}
        </div>
        <p
          aria-live="polite"
          className={`mt-1 text-xs tabular-nums ${mixOk ? "text-ink-muted" : "text-warning-text"}`}
        >
          {total === null ? "Total: —" : `Total: ${formatBps(total)}`}
          {total !== null && !mixOk ? " — it must total 100%" : ""}
        </p>
      </fieldset>

      <FormActions
        submitting={submitting}
        error={error}
        submitLabel="Save as a new version"
        onCancel={onCancel}
      />
    </form>
  );
}

function Summary({ version }: { version: Assumptions }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {RATE_FIELDS.map(([field, label]) => (
        <div key={field} className="contents">
          <dt className="text-ink-secondary">{label}</dt>
          <dd className="tabular-nums">{formatBps(version[field])}</dd>
        </div>
      ))}
      <dt className="text-ink-secondary">Healthcare a year before 65</dt>
      <dd className="tabular-nums">
        {version.pre65_healthcare_annual_cents != null
          ? formatCurrency(version.pre65_healthcare_annual_cents)
          : "not stated"}
      </dd>
      <dt className="text-ink-secondary">Risk tolerance</dt>
      <dd>{version.risk_tolerance}</dd>
      <dt className="text-ink-secondary">Target mix</dt>
      <dd className="tabular-nums">
        {MIX_FIELDS.map(
          ([field, label]) => `${label} ${formatBps(version[field], { decimals: 0 })}`,
        ).join(" · ")}
      </dd>
    </dl>
  );
}

export default function PlanningPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [history, setHistory] = useState<Assumptions[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([apiFetch("/planning/profile"), apiFetch("/planning/assumptions")])
      .then(([loadedProfile, versions]) => {
        if (!live) return;
        setProfile(loadedProfile);
        setHistory(versions);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, []);

  if (profile === null || history === null) {
    if (error) return <ErrorState title="Planning unavailable" detail={error} />;
    return <Skeleton className="h-64 w-full" />;
  }

  const [current, ...earlier] = history;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <h1 className="text-xl font-medium tracking-tight">Planning</h1>

      <section
        aria-label="Your profile"
        className="border-hairline bg-surface-1 rounded-xl border p-4"
      >
        <h2 className="text-ink-secondary mb-3 text-sm">Your profile</h2>
        <ProfileForm profile={profile} onSaved={setProfile} />
      </section>

      <section
        aria-label="Assumptions"
        className="border-hairline bg-surface-1 rounded-xl border p-4"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-ink-secondary text-sm">
            Assumptions in use
            {current?.is_default ? (
              <span className="bg-surface-2 text-ink-secondary ml-2 rounded px-1.5 py-0.5 text-xs">
                Defaults
              </span>
            ) : null}
          </h2>
          {editing || !current ? null : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
            >
              Change
            </button>
          )}
        </div>
        {current ? (
          editing ? (
            <AssumptionsForm
              current={current}
              onSaved={(version) => {
                setHistory((list) => [version, ...(list ?? [])]);
                setEditing(false);
              }}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <Summary version={current} />
          )
        ) : (
          <p className="text-ink-secondary text-sm">No assumptions recorded.</p>
        )}
      </section>

      {earlier.length > 0 ? (
        <section aria-label="Earlier versions">
          <h2 className="text-ink-secondary mb-1 text-sm">Earlier versions</h2>
          <ul className="divide-hairline divide-y">
            {earlier.map((version) => (
              <li key={version.id} className="py-2 text-xs">
                <span className="text-ink">
                  {formatDate(version.effective_from.slice(0, 10))}
                  {version.is_default ? " · defaults" : ""}
                </span>
                <span className="text-ink-secondary">
                  {" "}
                  · return {formatBps(version.expected_real_return_bps)} · inflation{" "}
                  {formatBps(version.inflation_bps)} · {version.risk_tolerance}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
