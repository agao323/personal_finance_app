"use client";

/**
 * One account: what it holds, who owns how much of it and since when, and how it got
 * where it is.
 *
 * The stake table is the reason this page exists in the shape it does. A bare "50%"
 * is not checkable — effective dates are what let you see that a stake was entered
 * against the wrong date, which is otherwise invisible until a historical chart looks
 * wrong months later and there is nothing left to compare it against.
 *
 * The balance history is **raw**, not ownership-adjusted: `/accounts/{id}/history`
 * takes no view scope, and a line silently drawn at 50% under a heading that does not
 * say so is the kind of quiet wrongness this app is built to avoid. The heading says
 * so.
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";

import { KIND_LABELS, SUBTYPE_LABELS, isSplit, type Account } from "@/components/account-row";
import { BalanceForm } from "@/components/forms/balance-form";
import { StakeForm } from "@/components/forms/stake-form";
import { Sparkline } from "@/components/charts/sparkline";
import { EmptyState, ErrorState, Skeleton, StaleBadge } from "@/components/states";
import { TransactionTable, type TransactionRow } from "@/components/transaction-table";
import { ViewToggle, useViewScope } from "@/components/view-toggle";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatBps, formatCurrency, formatDate } from "@/lib/format";

type Detail = ResponseOf<"/accounts/{account_id}", "get">;
type History = ResponseOf<"/accounts/{account_id}/history", "get">;
type Stake = Detail["stakes"][number];

/**
 * A stake's date range in prose.
 *
 * Ranges are half-open — `effective_to` is the first day the stake no longer applies
 * — so the readable end is the day before. Printing the raw bound would say a stake
 * ended on a day it was still in force, and off-by-one in an ownership range is
 * exactly the error this table exists to make visible.
 */
export function stakeRange(stake: Stake): string {
  if (!stake.effective_to) return `${formatDate(stake.effective_from)} — now`;
  const end = new Date(`${stake.effective_to}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() - 1);
  return `${formatDate(stake.effective_from)} — ${formatDate(end.toISOString().slice(0, 10))}`;
}

export default function AccountDetailPage({ params }: PageProps<"/accounts/[id]">) {
  // `use` rather than an async server component: everything below fetches on the
  // client through the proxy, and splitting the page in two to unwrap one string
  // would buy nothing.
  const { id } = use(params);
  return <AccountDetailView accountId={id} />;
}

/** Exported so tests render it without having to resolve a params promise. */
export function AccountDetailView({ accountId }: { accountId: string }) {
  const [view, setView] = useViewScope();
  // Bumped after any write, to refetch the account and its history rather than
  // patching state — these figures are derived server-side and guessing at the new
  // ones in the browser is how the two drift.
  const [revision, setRevision] = useState(0);
  const [panel, setPanel] = useState<"balance" | "stake" | "close" | null>(null);
  const [detail, setDetail] = useState<{
    key: string;
    data: Detail | null;
    error: string | null;
  } | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [rows, setRows] = useState<TransactionRow[] | null>(null);

  useEffect(() => {
    let live = true;
    const key = `${accountId}|${view}`;
    apiFetch("/accounts/{account_id}", { params: { account_id: accountId }, query: { view } })
      .then((data) => {
        if (live) setDetail({ key, data, error: null });
      })
      .catch((cause: unknown) => {
        if (live) {
          setDetail({
            key,
            data: null,
            error: cause instanceof Error ? cause.message : "Unknown error",
          });
        }
      });
    return () => {
      live = false;
    };
  }, [accountId, view, revision]);

  // History and transactions carry no view scope, so they are fetched once per
  // account rather than again on every toggle.
  useEffect(() => {
    let live = true;
    apiFetch("/accounts/{account_id}/history", { params: { account_id: accountId } })
      .then((data) => {
        if (live) setHistory(data);
      })
      .catch(() => {
        // The sparkline is an enhancement; the balance above it is the fact. A
        // failure here hides the picture rather than the page.
        if (live) setHistory({ account_id: Number(accountId), points: [] });
      });

    apiFetch("/transactions", { query: { account_id: Number(accountId), limit: 25 } })
      .then((data) => {
        if (live) setRows(data.items);
      })
      .catch(() => {
        if (live) setRows([]);
      });

    return () => {
      live = false;
    };
  }, [accountId, revision]);

  const error = detail?.error ?? null;
  const account = detail?.data ?? null;

  if (error) {
    return (
      <div>
        <BackLink />
        <div className="mt-4">
          <ErrorState title="Account unavailable" detail={error} />
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div>
        <BackLink />
        <Skeleton className="mt-4 h-56 w-full" />
      </div>
    );
  }

  return (
    <div>
      <BackLink />

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-medium tracking-tight">{account.name}</h1>
          <p className="text-ink-muted mt-1 text-sm">
            {account.institution ? `${account.institution.name} · ` : ""}
            {SUBTYPE_LABELS[account.subtype]} · {KIND_LABELS[account.kind]}
            {account.closed_at ? ` · closed ${formatDate(account.closed_at)}` : ""}
          </p>
        </div>
        <ViewToggle view={view} onChange={setView} />
      </div>

      <BalanceCard
        account={account}
        history={history}
        onRecordBalance={account.closed_at ? undefined : () => setPanel("balance")}
      />

      <ManageAccount
        account={account}
        panel={panel}
        onPanel={setPanel}
        onChanged={() => {
          setPanel(null);
          setRevision((current) => current + 1);
        }}
      />

      <StakeTable stakes={account.stakes} />

      <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        <h2 className="text-ink-secondary text-sm">Recent transactions</h2>
        <div className="mt-3">
          {rows === null ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <TransactionTable
              rows={rows}
              caption={`Recent transactions for ${account.name}`}
              emptyTitle="No transactions on this account"
              emptyDetail="Balances can be recorded without transactions — an investment account tracked by value alone has history here but nothing to list."
            />
          )}
        </div>
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/accounts" className="text-ink-secondary hover:text-ink text-sm">
      ← All accounts
    </Link>
  );
}

function BalanceCard({
  account,
  history,
  onRecordBalance,
}: {
  account: Detail;
  history: History | null;
  /** Omitted for a closed account, which has nothing left to record. */
  onRecordBalance?: () => void;
}) {
  const adjusted = account.adjusted_balance_cents;
  const points = history?.points ?? [];
  const first = points[0];
  const last = points.at(-1);

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div>
          <h2 className="text-ink-secondary text-sm">Balance</h2>
          {adjusted === null || adjusted === undefined ? (
            <p className="text-ink-muted mt-2 text-sm">
              No balance on record{account.closed_at ? " — this account is closed." : "."}
            </p>
          ) : (
            <>
              <p className="mt-1 text-3xl font-medium tracking-tight">{formatCurrency(adjusted)}</p>
              {isSplit(account as Account) ? (
                <p className="text-ink-secondary mt-1 text-sm">
                  {formatBps(account.current_stake_bps ?? 0)} of{" "}
                  {formatCurrency(account.balance_cents as number)}
                </p>
              ) : null}
              {account.balance_as_of ? (
                <p className="text-ink-muted mt-1 text-xs">
                  as of {formatDate(account.balance_as_of)}
                </p>
              ) : null}
            </>
          )}

          {account.is_stale && account.balance_as_of ? (
            <div className="mt-3">
              <StaleBadge asOf={account.balance_as_of} />
              <p className="text-ink-secondary mt-1 text-sm">
                This balance is being carried forward.{" "}
                {onRecordBalance ? (
                  <button
                    type="button"
                    onClick={onRecordBalance}
                    className="text-accent underline underline-offset-4"
                  >
                    Record a newer one
                  </button>
                ) : null}
              </p>
            </div>
          ) : null}
        </div>

        {points.length > 0 ? (
          <div className="min-w-0">
            {/* Named raw, because it is: the history endpoint has no view scope. */}
            <h3 className="text-ink-secondary text-xs">Raw balance history</h3>
            <div className="mt-1">
              <Sparkline points={points} />
            </div>
            <div className="text-ink-muted mt-1 flex justify-between gap-4 text-xs tabular-nums">
              <span>{formatCurrency(first.balance_cents)}</span>
              <span>{formatCurrency(last!.balance_cents)}</span>
            </div>
          </div>
        ) : null}
      </div>

      {/* The sparkline is a shape; this is the data. */}
      {points.length > 0 ? (
        <table className="sr-only">
          <caption>Raw balance history for {account.name}</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Balance</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.as_of}>
                <th scope="row">{formatDate(point.as_of)}</th>
                <td>{formatCurrency(point.balance_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function StakeTable({ stakes }: { stakes: Stake[] }) {
  if (stakes.length === 0) {
    return (
      <section className="mt-4">
        <EmptyState
          title="No ownership stake recorded"
          detail="Every account should have one. This account will not contribute to net worth until it does."
        />
      </section>
    );
  }

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <h2 className="text-ink-secondary text-sm">Ownership</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Ownership stakes and the dates they applied</caption>
          <thead>
            <tr className="border-hairline text-ink-secondary border-b text-left">
              <th scope="col" className="py-2 pr-3 font-medium">
                Owner
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Share
              </th>
              <th scope="col" className="py-2 font-medium">
                In effect
              </th>
            </tr>
          </thead>
          <tbody>
            {stakes.map((stake) => (
              <tr key={stake.id} className="border-hairline/60 border-b last:border-0">
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {stake.owner_display_name}
                </th>
                <td className="py-2 pr-3 tabular-nums">{formatBps(stake.percentage_bps)}</td>
                <td className="text-ink-secondary py-2 whitespace-nowrap">{stakeRange(stake)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/**
 * The write actions: record a balance, change ownership, close the account.
 *
 * One panel open at a time, and each closed by default. These are the three ways to
 * change what an account claims, and a page that presents all three expanded reads as
 * a form rather than as a record.
 */
function ManageAccount({
  account,
  panel,
  onPanel,
  onChanged,
}: {
  account: Detail;
  panel: "balance" | "stake" | "close" | null;
  onPanel: (next: "balance" | "stake" | "close" | null) => void;
  onChanged: () => void;
}) {
  // There is no /users endpoint, so the owners we can name are the ones already on
  // this account. Ticket 034 brings a real session and this becomes "you".
  const owners = [
    ...new Map(
      account.stakes.map((stake) => [
        stake.owner_user_id,
        { id: stake.owner_user_id, name: stake.owner_display_name },
      ]),
    ).values(),
  ];
  const [ownerId, setOwnerId] = useState(() => owners[0]?.id ?? null);

  if (account.closed_at) {
    return (
      <section className="border-hairline mt-4 rounded-xl border border-dashed p-4">
        <p className="text-ink-secondary text-sm">
          This account was closed on {formatDate(account.closed_at)}. It keeps its history and
          counts toward no total.
        </p>
      </section>
    );
  }

  return (
    <section className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-3">
        {(
          [
            { key: "balance", label: "Record a balance" },
            { key: "stake", label: "Change ownership" },
            { key: "close", label: "Close account" },
          ] as const
        ).map((action) => (
          <button
            key={action.key}
            type="button"
            aria-expanded={panel === action.key}
            onClick={() => onPanel(panel === action.key ? null : action.key)}
            className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 text-sm transition-colors"
          >
            {action.label}
          </button>
        ))}
      </div>

      {panel === "balance" ? (
        <div className="mt-4">
          <BalanceForm
            accountId={account.id}
            accountName={account.name}
            isLiability={account.kind === "liability"}
            onRecorded={onChanged}
          />
        </div>
      ) : null}

      {panel === "stake" ? (
        <div className="mt-4">
          {owners.length > 1 ? (
            <label className="text-ink-secondary mb-3 block text-sm">
              Whose share
              <select
                value={ownerId ?? ""}
                onChange={(event) => setOwnerId(Number(event.target.value))}
                className="border-hairline bg-surface-1 text-ink ml-2 rounded-md border px-2 py-1"
              >
                {owners.map((owner) => (
                  <option key={owner.id} value={owner.id}>
                    {owner.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {ownerId === null ? (
            <p className="text-ink-secondary text-sm">
              This account has no stake to change. That should not happen — every account gets one
              when it is created.
            </p>
          ) : (
            <StakeForm
              accountId={account.id}
              stakes={account.stakes}
              ownerUserId={ownerId}
              ownerName={owners.find((owner) => owner.id === ownerId)?.name ?? "Owner"}
              onSaved={onChanged}
              onCancel={() => onPanel(null)}
            />
          )}
        </div>
      ) : null}

      {panel === "close" ? (
        <div className="mt-4">
          <CloseAccount account={account} onClosed={onChanged} onCancel={() => onPanel(null)} />
        </div>
      ) : null}
    </section>
  );
}

/**
 * Close an account.
 *
 * Not a delete, and the copy says so: the history stays and the balance stops
 * counting. Those are different enough that a confirmation which only said "are you
 * sure?" would leave the reader guessing which one they were agreeing to.
 */
function CloseAccount({
  account,
  onClosed,
  onCancel,
}: {
  account: Detail;
  onClosed: () => void;
  onCancel: () => void;
}) {
  const [closedAt, setClosedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function close() {
    setSubmitting(true);
    setFailure(null);
    try {
      await apiFetch("/accounts/{account_id}", {
        method: "patch",
        params: { account_id: account.id },
        body: { closed_at: closedAt },
      });
      onClosed();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "The account was not closed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="border-warning/40 rounded-lg border p-3">
      <p className="text-sm font-medium">Close {account.name}?</p>
      <ul className="text-ink-secondary mt-2 list-disc space-y-1 pl-5 text-sm">
        <li>Its balance stops counting toward net worth from the closing date.</li>
        <li>Its transactions and balance history are kept, and still appear in spending.</li>
        <li>It moves to the closed section on the accounts list. Nothing is deleted.</li>
      </ul>

      <label className="text-ink-secondary mt-3 block text-sm">
        Closed on
        <input
          type="date"
          value={closedAt}
          onChange={(event) => setClosedAt(event.target.value)}
          className="border-hairline bg-surface-1 text-ink ml-2 rounded-md border px-2 py-1"
        />
      </label>

      {failure ? (
        <p role="alert" className="text-critical-text mt-2 text-sm">
          {failure}
        </p>
      ) : null}

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={close}
          disabled={submitting}
          className="border-critical/40 text-critical-text rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {submitting ? "Closing…" : "Close account"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-secondary hover:text-ink text-sm underline underline-offset-4"
        >
          Keep it open
        </button>
      </div>
    </div>
  );
}
