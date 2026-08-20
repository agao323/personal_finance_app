"use client";

/**
 * Who is in the household.
 *
 * Adding someone is three systems deep and only one of them is here: a `users` row,
 * an entry on the Cloudflare Access policy, and their own passkey. The Access step
 * cannot be automated from inside the app, so this screen states it rather than
 * letting you discover it when the invitation silently never loads for them.
 */

import { useCallback, useEffect, useState } from "react";

import { Field, FormActions, inputClass } from "@/components/forms/fields";
import { ErrorState, Skeleton } from "@/components/states";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Member = ResponseOf<"/members", "get">[number];

export default function HouseholdPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [invitation, setInvitation] = useState<{ url: string; expires: string } | null>(null);

  useEffect(() => {
    let live = true;
    apiFetch("/members")
      .then((data) => {
        if (live) {
          setMembers(data);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (live) setError(cause instanceof Error ? cause.message : "Unknown error");
      });
    return () => {
      live = false;
    };
  }, [revision]);

  const reload = useCallback(() => setRevision((current) => current + 1), []);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/members", {
        method: "post",
        body: { email: email.trim(), display_name: displayName.trim() },
      });
      setEmail("");
      setDisplayName("");
      reload();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That member was not added.");
    } finally {
      setBusy(false);
    }
  }

  async function invite(member: Member) {
    setBusy(true);
    setError(null);
    setInvitation(null);
    try {
      const created = await apiFetch("/members/{member_id}/invitation", {
        method: "post",
        params: { member_id: member.id },
      });
      // Shown once, because only its hash is stored. Reissuing is cheap; being able
      // to read it back later would mean every backup carries a live credential.
      setInvitation({
        url: `${globalThis.location.origin}/invitation?token=${encodeURIComponent(created.token)}`,
        expires: created.expires_at,
      });
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "No invitation was created.");
    } finally {
      setBusy(false);
    }
  }

  async function setActive(member: Member, isActive: boolean) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/members/{member_id}", {
        method: "patch",
        params: { member_id: member.id },
        body: { is_active: isActive },
      });
      reload();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That did not change.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-medium tracking-tight">Household</h1>
      <p className="text-ink-secondary mt-2 text-sm">
        Everyone here sees every account. Only the <em>money</em> splits, by ownership stake.
      </p>

      {error ? (
        <div className="mt-4">
          <ErrorState title="That did not work" detail={error} />
        </div>
      ) : null}

      {invitation ? (
        <div className="border-accent/40 bg-surface-1 mt-4 rounded-xl border p-4">
          <p className="text-sm font-medium">Invitation link — copy it now</p>
          <p className="text-ink-secondary mt-1 text-sm">
            It is shown once and cannot be retrieved later. Valid until{" "}
            {formatDate(invitation.expires.slice(0, 10))}. Send it however you like; it only works
            from behind Cloudflare Access, so it is not the only thing protecting the account.
          </p>
          <code className="border-hairline bg-surface-2 mt-3 block overflow-x-auto rounded-lg border p-2 text-xs">
            {invitation.url}
          </code>
        </div>
      ) : null}

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        {members === null && !error ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <ul>
            {(members ?? []).map((member) => (
              <li
                key={member.id}
                className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-3 last:border-0"
              >
                <span className="text-sm">
                  <span className="block font-medium">
                    {member.display_name}
                    {!member.is_active ? (
                      <span className="border-hairline text-ink-muted ml-2 rounded border px-1.5 py-px text-[10px] tracking-wide uppercase">
                        inactive
                      </span>
                    ) : null}
                  </span>
                  <span className="text-ink-muted block text-xs">{member.email}</span>
                  <span className="text-ink-muted block text-xs">
                    {member.passkey_count === 0
                      ? "No passkey yet — they cannot sign in"
                      : `${member.passkey_count} passkey${member.passkey_count === 1 ? "" : "s"}`}
                  </span>
                </span>

                <span className="flex items-center gap-3 text-sm">
                  {member.passkey_count === 0 ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => invite(member)}
                      className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1.5 transition-colors disabled:opacity-50"
                    >
                      Create invitation
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setActive(member, !member.is_active)}
                    className="text-ink-secondary hover:text-ink underline underline-offset-4 disabled:opacity-50"
                  >
                    {member.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        onSubmit={add}
        noValidate
        className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4"
      >
        <h2 className="text-sm font-medium">Add someone</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field label="Email" hint="Must match their Cloudflare Access identity exactly.">
            {({ id, describedBy }) => (
              <input
                id={id}
                type="email"
                value={email}
                aria-describedby={describedBy}
                onChange={(event) => setEmail(event.target.value)}
                className={inputClass}
              />
            )}
          </Field>
          <Field label="Display name">
            {({ id }) => (
              <input
                id={id}
                type="text"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                className={inputClass}
              />
            )}
          </Field>
        </div>
        <FormActions submitting={busy} error={null} submitLabel="Add member" />
      </form>

      <div className="border-warning/40 mt-4 rounded-xl border p-4">
        <p className="text-sm font-medium">Two steps this screen cannot do</p>
        <ol className="text-ink-secondary mt-2 list-decimal space-y-1 pl-5 text-sm">
          <li>
            Add their email to the <strong>Cloudflare Access policy</strong>. Without it they never
            reach this app at all, which from their side looks exactly like being refused.
          </li>
          <li>Give them the invitation link, which they open to register their own passkey.</li>
        </ol>
      </div>
    </div>
  );
}
