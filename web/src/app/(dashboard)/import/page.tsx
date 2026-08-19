"use client";

/**
 * Import transactions from a CSV.
 *
 * The other way data gets in is by hand (031). This is the bulk path, and the one
 * that runs against real bank exports — which is why the wizard spends two of its four
 * steps showing you what it is about to do.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { CsvWizard } from "@/components/import/csv-wizard";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import type { AccountOption } from "@/components/transaction-filters";
import { apiFetch } from "@/lib/api";

export default function ImportPage() {
  const [accounts, setAccounts] = useState<AccountOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts")
      .then((data) => {
        if (!live) return;
        setAccounts(
          data.groups.flatMap((group) =>
            group.accounts.map((account) => ({ id: account.id, name: account.name })),
          ),
        );
      })
      .catch((cause: unknown) => {
        if (live) setError(cause instanceof Error ? cause.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div>
      <h1 className="text-xl font-medium tracking-tight">Import</h1>
      <p className="text-ink-muted mt-1 text-sm">
        Transactions from a bank or card export. Importing the same file twice is safe — rows are
        matched, not appended.
      </p>

      <div className="mt-4">
        {error ? (
          <ErrorState title="Accounts unavailable" detail={error} />
        ) : accounts === null ? (
          <Skeleton className="h-64 w-full" />
        ) : accounts.length === 0 ? (
          <EmptyState
            title="No accounts to import into"
            detail="An import needs an account to attach the transactions to."
            action={
              <Link
                href="/accounts/new"
                className="border-hairline hover:bg-surface-2 inline-block rounded-lg border px-3 py-1.5 text-sm transition-colors"
              >
                Create an account
              </Link>
            }
          />
        ) : (
          <CsvWizard accounts={accounts} />
        )}
      </div>
    </div>
  );
}
