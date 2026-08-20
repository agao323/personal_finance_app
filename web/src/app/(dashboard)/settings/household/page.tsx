"use client";

/**
 * Who is in the household.
 *
 * Adding someone is two systems deep and only one of them is here: a `users` row, and
 * their email on the Cloudflare Access policy. The Access step cannot be automated from
 * inside the app, so this screen states it rather than letting you discover it when
 * they hit a refusal that looks identical to not existing.
 *
 * There used to be a third step — their own passkey, delivered as an invitation link.
 * Ticket 047b removed it: Access authenticates them, so there is nothing left to hand
 * over. See docs/adr/0007-drop-passkeys.md.
 */

import { useCallback, useEffect, useState } from "react";

import { Field, FormActions, inputClass } from "@/components/forms/fields";
import { ErrorState, Skeleton } from "@/components/states";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";

type Member = ResponseOf<"/members", "get">[number];

export default function HouseholdPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");

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
                </span>

                <span className="flex items-center gap-3 text-sm">
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
        <p className="text-sm font-medium">One step this screen cannot do</p>
        <p className="text-ink-secondary mt-2 text-sm">
          Add their email to the <strong>Cloudflare Access policy</strong>, exactly as typed above.
          Without it they never reach this app at all — which from their side looks identical to
          being refused, and there is nothing here that would tell either of you which it was.
        </p>
      </div>
    </div>
  );
}
