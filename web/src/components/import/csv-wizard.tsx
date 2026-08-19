"use client";

/**
 * Upload → map → preview → commit.
 *
 * Four steps with working back navigation, because the whole value of the preview is
 * that you can disagree with it. A wizard you can only go forward through turns
 * "that merchant column looks wrong" into "import it and find out".
 *
 * The file is read once, into text. The preview endpoint wants multipart and the
 * commit endpoint wants the raw CSV in JSON, so keeping the text means a re-preview
 * after a mapping change does not ask the reader to pick the file again.
 */

import { useCallback, useState } from "react";

import {
  ColumnMapper,
  type ColumnMapping,
  type MappingSource,
} from "@/components/import/column-mapper";
import { ImportPreview, type Preview } from "@/components/import/import-preview";
import { ErrorState, Skeleton } from "@/components/states";
import type { AccountOption } from "@/components/transaction-filters";
import { apiFetch } from "@/lib/api";

export type Step = "file" | "map" | "preview" | "done";

export const STEPS: { key: Step; label: string }[] = [
  { key: "file", label: "Choose a file" },
  { key: "map", label: "Map columns" },
  { key: "preview", label: "Check the result" },
  { key: "done", label: "Done" },
];

/** The header row, so the mapper can offer real column names. */
export function headersOf(content: string): string[] {
  const firstLine = content.split(/\r?\n/, 1)[0] ?? "";
  if (!firstLine) return [];
  // Good enough for a header row: quoted headers containing commas are vanishingly
  // rare, and a wrong split here shows up immediately as nonsense in the picker
  // rather than as a silently wrong import.
  return firstLine
    .split(",")
    .map((header) => header.trim().replace(/^"|"$/g, ""))
    .filter(Boolean);
}

function message(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

export function CsvWizard({ accounts }: { accounts: AccountOption[] }) {
  const [step, setStep] = useState<Step>("file");
  const [accountId, setAccountId] = useState<number | null>(null);
  const [fileName, setFileName] = useState("");
  const [content, setContent] = useState("");
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [source, setSource] = useState<MappingSource>("detected");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<{
    created: number;
    updated: number;
    skipped: number;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMapping, setSaveMapping] = useState(true);

  const runPreview = useCallback(
    async (id: number, csv: string, override: ColumnMapping | null) => {
      setBusy(true);
      setError(null);
      try {
        const form = new FormData();
        form.append("account_id", String(id));
        // A File, not a Blob with a filename argument: the field is a file upload,
        // and a Blob loses the name on some multipart encoders.
        form.append("file", new File([csv], fileName || "import.csv", { type: "text/csv" }));
        if (override) form.append("mapping", JSON.stringify(override));

        const next = await apiFetch("/import/csv/preview", { method: "post", formData: form });
        setPreview(next);
        setMapping(next.detected_mapping);
        setSource(next.mapping_source ?? "detected");
        return next;
      } catch (cause: unknown) {
        // A file with no header or an unreadable encoding has no rows to show and no
        // mapping to correct, so it fails here rather than producing an empty step.
        setError(message(cause, "That file could not be read."));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [fileName],
  );

  async function onFileChosen(file: File) {
    setFileName(file.name);
    const text = await file.text();
    setContent(text);
    setPreview(null);
    setMapping(null);
    setResult(null);
    if (accountId === null) return;
    const next = await runPreview(accountId, text, null);
    if (next) setStep("map");
  }

  async function commit() {
    if (accountId === null || !mapping) return;
    setBusy(true);
    setError(null);
    try {
      const outcome = await apiFetch("/import/csv/commit", {
        method: "post",
        body: {
          account_id: accountId,
          content,
          mapping,
          ...(saveMapping ? { save_mapping_as: fileName.replace(/\.csv$/i, "") || "default" } : {}),
        },
      });
      setResult(outcome);
      setStep("done");
    } catch (cause: unknown) {
      setError(message(cause, "The import did not run."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <StepBar current={step} />

      {error ? (
        <div className="mt-4">
          <ErrorState title="Import problem" detail={error} />
        </div>
      ) : null}

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        {step === "file" ? (
          <FileStep
            accounts={accounts}
            accountId={accountId}
            onAccount={setAccountId}
            fileName={fileName}
            busy={busy}
            onFile={onFileChosen}
          />
        ) : null}

        {step === "map" ? (
          busy && !mapping ? (
            <Skeleton className="h-48 w-full" />
          ) : mapping ? (
            <>
              <ColumnMapper
                headers={headersOf(content)}
                mapping={mapping}
                source={source}
                onChange={setMapping}
              />
              <StepActions
                busy={busy}
                backLabel="Choose a different file"
                onBack={() => setStep("file")}
                nextLabel="Check the result"
                onNext={async () => {
                  const next = await runPreview(accountId as number, content, mapping);
                  if (next) setStep("preview");
                }}
              />
            </>
          ) : null
        ) : null}

        {step === "preview" ? (
          busy ? (
            <Skeleton className="h-64 w-full" />
          ) : preview ? (
            <>
              <ImportPreview preview={preview} />
              <label className="mt-4 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={saveMapping}
                  onChange={(event) => setSaveMapping(event.target.checked)}
                />
                Remember this mapping for{" "}
                {accounts.find((a) => a.id === accountId)?.name ?? "this account"}
              </label>
              <StepActions
                busy={busy}
                backLabel="Change the mapping"
                onBack={() => setStep("map")}
                nextLabel={
                  preview.will_create + preview.will_update === 0 ? "Import anyway" : "Import"
                }
                onNext={commit}
              />
            </>
          ) : null
        ) : null}

        {step === "done" && result ? (
          <DoneStep
            result={result}
            onAgain={() => {
              setStep("file");
              setFileName("");
              setContent("");
              setPreview(null);
              setMapping(null);
              setResult(null);
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function StepBar({ current }: { current: Step }) {
  const index = STEPS.findIndex((step) => step.key === current);
  return (
    <ol className="text-ink-muted flex flex-wrap items-center gap-2 text-sm">
      {STEPS.map((step, position) => (
        <li key={step.key} className="flex items-center gap-2">
          {position > 0 ? <span aria-hidden="true">›</span> : null}
          <span
            aria-current={step.key === current ? "step" : undefined}
            className={
              position === index
                ? "text-ink font-medium"
                : position < index
                  ? "text-ink-secondary"
                  : ""
            }
          >
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

function FileStep({
  accounts,
  accountId,
  onAccount,
  fileName,
  busy,
  onFile,
}: {
  accounts: AccountOption[];
  accountId: number | null;
  onAccount: (id: number) => void;
  fileName: string;
  busy: boolean;
  onFile: (file: File) => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-ink-secondary mb-1 block text-sm">Import into</span>
        <select
          aria-label="Import into"
          value={accountId ?? ""}
          onChange={(event) => onAccount(Number(event.target.value))}
          className="border-hairline bg-surface-1 text-ink w-full rounded-md border px-2 py-1.5 text-sm sm:w-72"
        >
          <option value="">— pick an account —</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="text-ink-secondary mb-1 block text-sm">CSV file</span>
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV file"
          disabled={accountId === null || busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
          }}
          className="text-sm disabled:opacity-50"
        />
        {accountId === null ? (
          <span className="text-ink-muted mt-1 block text-xs">Pick an account first.</span>
        ) : null}
        {fileName ? <span className="text-ink-muted mt-1 block text-xs">{fileName}</span> : null}
      </label>

      <p className="text-ink-muted text-xs">
        Nothing is written until you have seen what it would do. The next two steps are a dry run.
      </p>
    </div>
  );
}

function StepActions({
  busy,
  backLabel,
  onBack,
  nextLabel,
  onNext,
}: {
  busy: boolean;
  backLabel: string;
  onBack: () => void;
  nextLabel: string;
  onNext: () => void;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={busy}
        onClick={onNext}
        className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
      >
        {busy ? "Working…" : nextLabel}
      </button>
      <button
        type="button"
        onClick={onBack}
        className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
      >
        {backLabel}
      </button>
    </div>
  );
}

function DoneStep({
  result,
  onAgain,
}: {
  result: { created: number; updated: number; skipped: number };
  onAgain: () => void;
}) {
  const changed = result.created + result.updated;
  return (
    <div>
      <p className="text-lg font-medium">
        {changed === 0 ? "Nothing changed" : `${changed} transactions written`}
      </p>
      <p className="text-ink-secondary mt-1 text-sm">
        {result.created} new, {result.updated} changed, {result.skipped} already up to date.
        {changed === 0 ? " This file had already been imported." : ""}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <button
          type="button"
          onClick={onAgain}
          className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors"
        >
          Import another file
        </button>
        <a href="/transactions" className="text-accent underline underline-offset-4">
          Review the transactions
        </a>
      </div>
    </div>
  );
}
