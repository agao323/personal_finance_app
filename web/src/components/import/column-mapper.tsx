"use client";

/**
 * Which CSV column means what.
 *
 * Every institution exports a different shape and none of them change it, so this
 * step is a one-time cost per account — which is exactly why it has to be correctable
 * rather than merely automatic. The API detects a mapping and remembers the one you
 * committed; this is where you disagree with it.
 *
 * The sign convention is here rather than in the preview because it *is* a mapping
 * decision: "Amount" means the opposite thing at a bank that writes withdrawals
 * positive, and no amount of looking at the number tells you which convention a file
 * uses without knowing what the row was.
 */

import type { components } from "@/lib/api-types";

export type ColumnMapping = components["schemas"]["ColumnMapping"];

export type MappingSource = "supplied" | "saved" | "detected" | string;

const FIELDS: { key: keyof ColumnMapping; label: string; required: boolean; hint?: string }[] = [
  { key: "posted_at", label: "Date", required: true },
  { key: "amount", label: "Amount", required: true },
  { key: "merchant", label: "Merchant", required: false },
  { key: "description", label: "Description", required: false },
  {
    key: "external_id",
    label: "Bank's own id",
    required: false,
    hint: "Used to recognise a row you have already imported. Left blank, one is derived from the row itself.",
  },
];

export function SourceNote({ source }: { source: MappingSource }) {
  if (source === "saved") {
    return (
      <p className="text-ink-secondary text-sm">
        Using the mapping saved for this account last time. Change anything that looks wrong.
      </p>
    );
  }
  if (source === "supplied") {
    return <p className="text-ink-secondary text-sm">Using your corrections to the mapping.</p>;
  }
  return (
    <p className="text-ink-secondary text-sm">
      Guessed from the header row. Check it before importing — a wrong column is silent.
    </p>
  );
}

export function ColumnMapper({
  headers,
  mapping,
  source,
  onChange,
}: {
  headers: string[];
  mapping: ColumnMapping;
  source: MappingSource;
  onChange: (next: ColumnMapping) => void;
}) {
  return (
    <div>
      <SourceNote source={source} />

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {FIELDS.map((field) => {
          const value = (mapping[field.key] as string | null | undefined) ?? "";
          return (
            <label key={field.key} className="block">
              <span className="text-ink-secondary mb-1 block text-sm">
                {field.label}
                {field.required ? "" : " (optional)"}
              </span>
              <select
                aria-label={field.label}
                value={value}
                onChange={(event) =>
                  onChange({ ...mapping, [field.key]: event.target.value || null })
                }
                className="border-hairline bg-surface-1 text-ink w-full rounded-md border px-2 py-1.5 text-sm"
              >
                <option value="">{field.required ? "— pick a column —" : "— none —"}</option>
                {headers.map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
              {field.hint ? (
                <span className="text-ink-muted mt-1 block text-xs">{field.hint}</span>
              ) : null}
            </label>
          );
        })}
      </div>

      <fieldset className="border-hairline mt-4 rounded-lg border p-3">
        <legend className="text-ink-secondary px-1 text-sm">Sign convention</legend>
        <p className="text-ink-muted text-xs">
          This app stores money you spend as negative. Pick whichever matches the file, then check
          the preview — a flipped sign turns spending into income and every total downstream is
          wrong.
        </p>
        <div className="mt-2 flex flex-wrap gap-4 text-sm">
          {[
            { value: false, label: "Spending is already negative" },
            { value: true, label: "Spending is positive — flip it" },
          ].map((option) => (
            <label key={String(option.value)} className="flex items-center gap-2">
              <input
                type="radio"
                name="invert_amount"
                checked={Boolean(mapping.invert_amount) === option.value}
                onChange={() => onChange({ ...mapping, invert_amount: option.value })}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
