"use client";

/**
 * The passkeys registered to this account.
 *
 * This screen exists because without it a new laptop is an incident. Registering a
 * passkey has always worked for a signed-in user — `/auth/register/options` takes the
 * current user, not just the bootstrap one — but the only button that called it lived
 * on the sign-in page and read as a first-run action. The capability was there and
 * unreachable.
 *
 * **Removing the last one is refused by the API**, and this screen says why before you
 * try. An account with no credential can only be recovered through the bootstrap
 * window, which shuts permanently the moment any credential exists — so there is no
 * undo behind that button.
 */

import { useCallback, useEffect, useState } from "react";

import { ErrorState, Skeleton } from "@/components/states";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { createCredential, isSupported } from "@/lib/webauthn";
import { formatDate } from "@/lib/format";

type Credential = ResponseOf<"/auth/credentials", "get">[number];

export default function PasskeysPage() {
  const [credentials, setCredentials] = useState<Credential[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let live = true;
    apiFetch("/auth/credentials")
      .then((data) => {
        if (live) {
          setCredentials(data);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (live) {
          setCredentials(null);
          setError(cause instanceof Error ? cause.message : "Unknown error");
        }
      });
    return () => {
      live = false;
    };
  }, [revision]);

  const reload = useCallback(() => setRevision((current) => current + 1), []);

  async function addDevice() {
    setBusy(true);
    setError(null);
    try {
      const started = await apiFetch("/auth/register/options", { method: "post" });
      const credential = await createCredential(started.options);
      await apiFetch("/auth/register/verify", {
        method: "post",
        body: { challenge_id: started.challenge_id, credential },
      });
      reload();
    } catch (cause: unknown) {
      setError(
        cause instanceof Error && cause.name === "NotAllowedError"
          ? "That was cancelled — nothing has changed."
          : cause instanceof Error
            ? cause.message
            : "The passkey was not registered.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(credential: Credential) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/auth/credentials/{credential_id}", {
        method: "delete",
        params: { credential_id: credential.id },
      });
      reload();
    } catch (cause: unknown) {
      // The API refuses to remove the last one with a 409 and an explanation. Showing
      // its message is better than inventing one that might drift from the rule.
      setError(cause instanceof Error ? cause.message : "The passkey was not removed.");
    } finally {
      setBusy(false);
    }
  }

  const onlyOne = (credentials?.length ?? 0) <= 1;

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-medium tracking-tight">Passkeys</h1>
      <p className="text-ink-secondary mt-2 text-sm">
        The devices that can sign in as you. Register one on each device you use — a passkey never
        leaves the device it was created on, so a new laptop needs its own.
      </p>

      {error ? (
        <div className="mt-4">
          <ErrorState title="That did not work" detail={error} />
        </div>
      ) : null}

      <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
        {credentials === null && !error ? (
          <Skeleton className="h-24 w-full" />
        ) : credentials ? (
          <ul>
            {credentials.map((credential) => (
              <li
                key={credential.id}
                className="border-hairline/60 flex flex-wrap items-center justify-between gap-3 border-b py-3 last:border-0"
              >
                <span className="text-sm">
                  <span className="block font-medium">
                    Registered {formatDate(credential.created_at.slice(0, 10))}
                    {credential.is_current ? (
                      <span className="border-hairline text-ink-muted ml-2 rounded border px-1.5 py-px text-[10px] tracking-wide uppercase">
                        this device
                      </span>
                    ) : null}
                  </span>
                  <span className="text-ink-muted block text-xs">
                    {credential.last_used_at
                      ? `Last used ${formatDate(credential.last_used_at.slice(0, 10))}`
                      : "Never used to sign in"}
                  </span>
                </span>

                <button
                  type="button"
                  disabled={busy || onlyOne}
                  onClick={() => remove(credential)}
                  title={
                    onlyOne
                      ? "Register another device first — removing your only passkey would lock you out."
                      : undefined
                  }
                  className="text-critical-text px-2 py-1 text-sm underline underline-offset-4 disabled:no-underline disabled:opacity-40"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy || !isSupported()}
            onClick={addDevice}
            className="bg-accent-bg text-accent-strong rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Waiting for your device…" : "Register this device"}
          </button>
          {!isSupported() ? (
            <span className="text-ink-muted text-xs">
              This browser has no passkey support, so it cannot register one.
            </span>
          ) : null}
        </div>
      </div>

      {onlyOne && credentials?.length === 1 ? (
        <p className="text-ink-secondary mt-3 text-sm">
          You have one passkey. Register a second device before removing it — an account with no
          passkey cannot be recovered from inside the app.
        </p>
      ) : null}
    </div>
  );
}
