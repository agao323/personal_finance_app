"use client";

/**
 * One account in the list.
 *
 * The balance shown large is the **ownership-adjusted** one, because that is the
 * figure that reaches net worth. The raw balance appears underneath it whenever the
 * two differ, phrased as "60% of $1,377.17" so the stake and the number it applies to
 * read as one fact rather than two that have to be reconciled. Where the stake is
 * 100% the second line is absent — repeating the same number twice teaches the reader
 * to stop looking at it, which defeats the point on the accounts where it matters.
 *
 * Liability balances are positive here, matching storage: net worth subtracts them.
 * Storing debt negative makes every aggregate ambiguous about whether the sign was
 * already applied — see docs/ARCHITECTURE.md#users-and-ownership.
 */

import Link from "next/link";

import type { ResponseOf } from "@/lib/api";
import { StaleBadge } from "@/components/states";
import { formatBps, formatCurrency } from "@/lib/format";

export type Account = ResponseOf<"/accounts", "get">["groups"][number]["accounts"][number];
export type AccountKind = ResponseOf<"/accounts", "get">["groups"][number]["kind"];

export const KIND_LABELS: Record<AccountKind, string> = {
  liquid_asset: "Liquid assets",
  illiquid_asset: "Illiquid assets",
  liability: "Liabilities",
};

/**
 * Display names for account subtypes.
 *
 * A map rather than title-casing the enum: "401k" is written "401(k)", "ira" is an
 * initialism, and "hsa" title-cases to "Hsa". Every one of those looks like a bug to
 * the person whose account it is.
 */
export const SUBTYPE_LABELS: Record<Account["subtype"], string> = {
  checking: "Checking",
  savings: "Savings",
  money_market: "Money market",
  cd: "CD",
  brokerage: "Brokerage",
  ira: "IRA",
  roth_ira: "Roth IRA",
  "401k": "401(k)",
  hsa: "HSA",
  "529": "529",
  real_estate: "Real estate",
  vehicle: "Vehicle",
  other_asset: "Other asset",
  credit_card: "Credit card",
  mortgage: "Mortgage",
  auto_loan: "Auto loan",
  student_loan: "Student loan",
  personal_loan: "Personal loan",
  other_liability: "Other liability",
};

/** True when the ownership stake actually changes the number on screen. */
export function isSplit(account: Account): boolean {
  return (
    account.adjusted_balance_cents !== null &&
    account.adjusted_balance_cents !== undefined &&
    account.balance_cents !== null &&
    account.balance_cents !== undefined &&
    account.adjusted_balance_cents !== account.balance_cents
  );
}

export function AccountRow({ account }: { account: Account }) {
  const closed = Boolean(account.closed_at);
  const adjusted = account.adjusted_balance_cents;
  const raw = account.balance_cents;

  return (
    <li className="border-hairline/60 border-b last:border-0">
      <Link
        href={`/accounts/${account.id}`}
        className="hover:bg-surface-2 focus-visible:ring-accent flex items-start justify-between gap-4 rounded-lg px-2 py-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{account.name}</span>
          <span className="text-ink-muted block truncate text-xs">
            {account.institution ? `${account.institution.name} · ` : ""}
            {SUBTYPE_LABELS[account.subtype]}
            {closed ? ` · closed ${account.closed_at}` : ""}
          </span>
        </span>

        <span className="shrink-0 text-right">
          {adjusted === null || adjusted === undefined ? (
            // A closed account keeps no in-force balance, and an account whose first
            // snapshot has not been recorded has none yet. Both are "no balance", and
            // "$0.00" would be a claim about money rather than about data.
            <span className="text-ink-muted text-sm">No balance</span>
          ) : (
            <>
              <span className="block text-sm font-medium tabular-nums">
                {formatCurrency(adjusted)}
              </span>
              {isSplit(account) ? (
                <span className="text-ink-muted block text-xs tabular-nums">
                  {formatBps(account.current_stake_bps ?? 0)} of {formatCurrency(raw as number)}
                </span>
              ) : null}
            </>
          )}
          {account.is_stale && account.balance_as_of ? (
            <span className="mt-1 block">
              <StaleBadge asOf={account.balance_as_of} />
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}
