"use client";

/**
 * Accounts, grouped by what a balance means for net worth.
 *
 * Group subtotals only — there is deliberately no grand total on this page. The API's
 * `total_cents` is the sum of every balance regardless of kind, which adds a mortgage
 * to a brokerage and produces a number that is not any quantity a person has. Net
 * worth is one figure computed in one place (`services/ownership.py`) and shown on
 * the dashboard; re-deriving it here from group subtotals would be a second code path
 * to the most important number in the app.
 *
 * Closed accounts are pulled out of their kind groups into their own section. They
 * already contribute nothing to the subtotals — a closed account has no in-force
 * balance — so leaving them among the open ones would show rows that look like they
 * count and don't.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AccountRow, KIND_LABELS, type Account, type AccountKind } from "@/components/account-row";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { ViewToggle, useViewScope } from "@/components/view-toggle";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/format";

type AccountList = ResponseOf<"/accounts", "get">;

/** The order the groups read in: what you can spend, what you own, what you owe. */
export const KIND_ORDER: AccountKind[] = ["liquid_asset", "illiquid_asset", "liability"];

export interface Partitioned {
  open: { kind: AccountKind; accounts: Account[]; totalCents: number; adjustedCents: number }[];
  closed: Account[];
}

/**
 * Split the API's groups into open groups and one closed section.
 *
 * The subtotals come from the API untouched. Recomputing them here by summing the
 * rows would be a second implementation of the ownership adjustment, and it would
 * round differently: the server rounds once per account, and a browser-side sum of
 * already-rounded values is not guaranteed to match.
 */
export function partition(list: AccountList | null): Partitioned {
  const open: Partitioned["open"] = [];
  const closed: Account[] = [];

  for (const kind of KIND_ORDER) {
    const group = list?.groups.find((candidate) => candidate.kind === kind);
    if (!group) continue;
    const live = group.accounts.filter((account) => !account.closed_at);
    closed.push(...group.accounts.filter((account) => account.closed_at));
    if (live.length > 0) {
      open.push({
        kind,
        accounts: live,
        totalCents: group.total_cents,
        adjustedCents: group.adjusted_total_cents,
      });
    }
  }

  return { open, closed };
}

export default function AccountsPage() {
  const [view, setView] = useViewScope();
  const [loaded, setLoaded] = useState<{
    key: string;
    data: AccountList | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    let live = true;
    apiFetch("/accounts", { query: { view, include_closed: true } })
      .then((data) => {
        if (live) setLoaded({ key: view, data, error: null });
      })
      .catch((cause: unknown) => {
        if (live) {
          setLoaded({
            key: view,
            data: null,
            error: cause instanceof Error ? cause.message : "Unknown error",
          });
        }
      });
    return () => {
      live = false;
    };
  }, [view]);

  const stale = loaded?.key !== view;
  const error = stale ? null : loaded?.error;
  const list = loaded?.error ? null : (loaded?.data ?? null);
  const { open, closed } = useMemo(() => partition(list), [list]);
  const empty = list !== null && open.length === 0 && closed.length === 0;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-medium tracking-tight">Accounts</h1>
        <div className="flex items-center gap-3">
          <Link
            href="/accounts/new"
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 text-sm transition-colors"
          >
            New account
          </Link>
          <ViewToggle view={view} onChange={setView} />
        </div>
      </div>

      {error ? (
        <div className="mt-4">
          <ErrorState title="Accounts unavailable" detail={error} />
        </div>
      ) : !list ? (
        <div className="mt-4 space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : empty ? (
        <div className="mt-4">
          <EmptyState
            title="No accounts yet"
            detail="Import a CSV from your bank to create accounts and their balance history, or add one by hand."
            action={
              <div className="flex flex-wrap justify-center gap-3">
                <Link
                  href="/import"
                  className="border-hairline hover:bg-surface-2 inline-block rounded-lg border px-3 py-1.5 text-sm transition-colors"
                >
                  Import transactions
                </Link>
                <Link
                  href="/accounts/new"
                  className="text-accent inline-block px-1 py-1.5 text-sm underline underline-offset-4"
                >
                  Add one by hand
                </Link>
              </div>
            }
          />
        </div>
      ) : (
        <div className={`mt-4 space-y-4 ${stale ? "opacity-60 transition-opacity" : ""}`}>
          {open.map((group) => (
            <KindGroup key={group.kind} group={group} view={view} />
          ))}
          {closed.length > 0 ? <ClosedSection accounts={closed} /> : null}
        </div>
      )}
    </div>
  );
}

function KindGroup({
  group,
  view,
}: {
  group: Partitioned["open"][number];
  view: "mine" | "household";
}) {
  const split = group.adjustedCents !== group.totalCents;

  return (
    <section className="border-hairline bg-surface-1 rounded-xl border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-ink-secondary text-sm">{KIND_LABELS[group.kind]}</h2>
        <div className="text-right">
          <p className="font-medium tabular-nums">{formatCurrency(group.adjustedCents)}</p>
          {/* The unadjusted subtotal, shown only where a stake actually moved it.
              Naming the scope matters: under "Household" the adjusted figure is the
              sum of every stake, which is a different claim from the viewer's share. */}
          {split ? (
            <p className="text-ink-muted text-xs tabular-nums">
              {view === "household" ? "household share of " : "your share of "}
              {formatCurrency(group.totalCents)}
            </p>
          ) : null}
        </div>
      </div>

      <ul className="mt-2">
        {group.accounts.map((account) => (
          <AccountRow key={account.id} account={account} />
        ))}
      </ul>
    </section>
  );
}

function ClosedSection({ accounts }: { accounts: Account[] }) {
  return (
    <section className="border-hairline rounded-xl border border-dashed p-4">
      <h2 className="text-ink-secondary text-sm">Closed</h2>
      <p className="text-ink-muted mt-1 text-xs">
        Kept for history. They hold no balance and count toward no total.
      </p>
      <ul className="mt-2">
        {accounts.map((account) => (
          <AccountRow key={account.id} account={account} />
        ))}
      </ul>
    </section>
  );
}
