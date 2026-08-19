"use client";

/**
 * Create an account by hand.
 *
 * The other way in is a CSV import (032), which creates accounts as a side effect of
 * having transactions for them. This is the path for the things no bank exports: a
 * property, a vehicle, a private loan — which is also why the opening balance and the
 * ownership stake are on this form rather than being someone else's problem later.
 */

import { useRouter } from "next/navigation";
import Link from "next/link";

import { AccountForm } from "@/components/forms/account-form";

export default function NewAccountPage() {
  const router = useRouter();

  return (
    <div className="max-w-xl">
      <Link href="/accounts" className="text-ink-secondary hover:text-ink text-sm">
        ← All accounts
      </Link>
      <h1 className="mt-3 text-xl font-medium tracking-tight">New account</h1>
      <p className="text-ink-muted mt-1 text-sm">
        For anything you track by value rather than by transactions. Bank and card accounts are
        usually easier to add by importing a CSV.
      </p>

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        <AccountForm
          onCreated={(account) => router.push(`/accounts/${account.id}`)}
          onCancel={() => router.push("/accounts")}
        />
      </div>
    </div>
  );
}
