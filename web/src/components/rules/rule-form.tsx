"use client";

/**
 * Write or edit a rule, with a preview of what it would hit.
 *
 * The preview is the whole point. Writing a pattern against your own transaction
 * history without seeing what it matches is how you re-categorise two years of data
 * and do not notice for a month — and the subtler the pattern, the more true that is,
 * which is exactly when a `LIKE`-flavoured approximation would stop agreeing with the
 * engine. `POST /rules/preview` runs the real matcher.
 *
 * It is explicit, not live-as-you-type: a preview firing on every keystroke would run
 * a half-written regex over the whole history repeatedly, and half-written regexes are
 * where the catastrophic ones come from.
 */

import { useState } from "react";

import { CategoryPicker, type Category } from "@/components/category-picker";
import { Field, FormActions, inputClass } from "@/components/forms/fields";
import { TransactionTable } from "@/components/transaction-table";
import { Skeleton } from "@/components/states";
import type { BodyOf, ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Rule = ResponseOf<"/rules", "get">[number];
export type MatchType = components["schemas"]["MatchType"];
type PreviewResult = ResponseOf<"/rules/preview", "post">;

export const MATCH_TYPES: { value: MatchType; label: string; hint: string }[] = [
  { value: "contains", label: "Contains", hint: "The merchant includes this text, anywhere." },
  { value: "starts_with", label: "Starts with", hint: "The merchant begins with this text." },
  { value: "equals", label: "Is exactly", hint: "The merchant is exactly this text." },
  { value: "regex", label: "Matches a regex", hint: "A regular expression. Case-insensitive." },
];

export interface RuleDraft {
  pattern: string;
  matchType: MatchType;
  categoryId: number | null;
}

export function draftFrom(rule: Rule | null, pattern = ""): RuleDraft {
  if (!rule) return { pattern, matchType: "contains", categoryId: null };
  return { pattern: rule.pattern, matchType: rule.match_type, categoryId: rule.category_id };
}

export function validateRule(draft: RuleDraft): { pattern?: string; categoryId?: string } {
  const errors: { pattern?: string; categoryId?: string } = {};
  if (!draft.pattern.trim()) errors.pattern = "Enter something to match on.";
  else if (draft.pattern.length > 255) errors.pattern = "Patterns are limited to 255 characters.";
  // A rule with no category has nothing to do. The API requires one.
  if (draft.categoryId === null) errors.categoryId = "Pick the category to apply.";
  return errors;
}

export function RuleForm({
  rule,
  initialPattern,
  categories,
  onSaved,
  onCancel,
}: {
  /** Null creates. */
  rule: Rule | null;
  initialPattern?: string;
  categories: Category[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<RuleDraft>(() => draftFrom(rule, initialPattern));
  const [errors, setErrors] = useState<{ pattern?: string; categoryId?: string }>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function runPreview() {
    if (!draft.pattern.trim()) {
      setErrors({ pattern: "Enter something to match on." });
      return;
    }
    setPreviewing(true);
    setFailure(null);
    try {
      setPreview(
        await apiFetch("/rules/preview", {
          method: "post",
          body: { pattern: draft.pattern, match_type: draft.matchType, limit: 20 },
        }),
      );
    } catch (cause: unknown) {
      // A rejected pattern is the preview working: it caught a regex that would have
      // been rejected on save, before the reader wondered why saving failed.
      setPreview(null);
      setFailure(cause instanceof Error ? cause.message : "That pattern could not be checked.");
    } finally {
      setPreviewing(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validateRule(draft);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setFailure(null);
    try {
      if (rule) {
        await apiFetch("/rules/{rule_id}", {
          method: "patch",
          params: { rule_id: rule.id },
          body: {
            pattern: draft.pattern,
            match_type: draft.matchType,
            category_id: draft.categoryId,
          },
        });
      } else {
        const body: BodyOf<"/rules", "post"> = {
          pattern: draft.pattern,
          match_type: draft.matchType,
          category_id: draft.categoryId as number,
        };
        await apiFetch("/rules", { method: "post", body });
      }
      onSaved();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The rule was not saved.");
    } finally {
      setSubmitting(false);
    }
  }

  const hint = MATCH_TYPES.find((option) => option.value === draft.matchType)?.hint;

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="When the merchant" error={errors.pattern} hint={hint}>
          {({ id, describedBy, invalid }) => (
            <div className="flex gap-2">
              <select
                aria-label="Match type"
                value={draft.matchType}
                onChange={(event) => {
                  setDraft({ ...draft, matchType: event.target.value as MatchType });
                  setPreview(null);
                }}
                className={`${inputClass} w-40`}
              >
                {MATCH_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                id={id}
                type="text"
                value={draft.pattern}
                placeholder="CORNER MARKET"
                aria-describedby={describedBy}
                aria-invalid={invalid}
                onChange={(event) => {
                  setDraft({ ...draft, pattern: event.target.value });
                  // A preview of the previous pattern beside a changed one is worse
                  // than none: it reads as confirmation of what is now on screen.
                  setPreview(null);
                }}
                className={inputClass}
              />
            </div>
          )}
        </Field>

        <Field label="Categorise it as" error={errors.categoryId}>
          {({ id }) => (
            <div id={id}>
              <CategoryPicker
                label="Categorise it as"
                categories={categories}
                value={draft.categoryId}
                onChange={(next) => setDraft({ ...draft, categoryId: next })}
                className="w-full"
              />
            </div>
          )}
        </Field>
      </div>

      <div className="mt-4">
        <button
          type="button"
          onClick={runPreview}
          disabled={previewing}
          className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
        >
          {previewing ? "Checking…" : "Check what this matches"}
        </button>
      </div>

      {previewing ? <Skeleton className="mt-3 h-24 w-full" /> : null}

      {preview ? (
        <div className="border-hairline mt-3 rounded-lg border p-3">
          <p className="text-sm font-medium">
            {preview.match_count === 0
              ? "Matches nothing yet"
              : `Matches ${preview.match_count} transaction${preview.match_count === 1 ? "" : "s"}`}
          </p>
          {preview.already_manual > 0 ? (
            <p className="text-ink-secondary mt-1 text-sm">
              {preview.already_manual} of them you categorised by hand, so this rule will leave
              those alone.
            </p>
          ) : null}
          {preview.match_count === 0 ? (
            <p className="text-ink-secondary mt-1 text-sm">
              It will still apply to anything imported later.
            </p>
          ) : (
            <div className="mt-3">
              <TransactionTable
                rows={preview.matches}
                caption={`Transactions matching ${draft.pattern}`}
              />
              {preview.match_count > preview.matches.length ? (
                <p className="text-ink-muted mt-2 text-xs">
                  Showing {preview.matches.length} of {preview.match_count}.
                </p>
              ) : null}
            </div>
          )}
        </div>
      ) : null}

      <FormActions
        submitting={submitting}
        error={failure}
        submitLabel={rule ? "Save rule" : "Create rule"}
        onCancel={onCancel}
      />
    </form>
  );
}
