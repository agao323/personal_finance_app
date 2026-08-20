"use client";

/**
 * Redeem an invitation: register your first passkey against your own account.
 *
 * Outside `(dashboard)` and public in `proxy.ts`, because the person opening it has no
 * session — that is the entire point. They have already passed Cloudflare Access to
 * get here, so the token in the URL is a second factor rather than the only one.
 *
 * The registration deliberately does **not** go through `/auth/register/*`. That route
 * registers a passkey for whoever is currently signed in, so an owner opening this link
 * in their own browser would bind the newcomer's authenticator to the owner's account —
 * silently wrong, because every ownership figure in this app is per-user.
 */

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { createCredential, isSupported } from "@/lib/webauthn";

export default function InvitationPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto mt-24 h-40 w-full max-w-md" />}>
      <RedeemScreen />
    </Suspense>
  );
}

export function RedeemScreen() {
  const search = useSearchParams();
  const token = search?.get("token") ?? "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);

  async function redeem() {
    setBusy(true);
    setError(null);
    try {
      const started = await apiFetch("/auth/invitation/redeem/options", {
        method: "post",
        body: { token },
      });
      const credential = await createCredential(started.options);
      const session = await apiFetch("/auth/invitation/redeem/verify", {
        method: "post",
        body: { token, challenge_id: started.challenge_id, credential },
      });
      setName(session.display_name);
      // Full navigation: the session cookie was just set and every cached render was
      // produced without it.
      globalThis.location.assign("/");
    } catch (cause: unknown) {
      setError(
        cause instanceof Error && cause.name === "NotAllowedError"
          ? "That was cancelled — nothing has changed."
          : cause instanceof Error
            ? cause.message
            : "That invitation could not be redeemed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-md">
      <h1 className="text-xl font-medium tracking-tight">Join the household</h1>

      {!token ? (
        <p role="alert" className="text-critical-text mt-3 text-sm">
          This link is missing its invitation code. Ask for a new link.
        </p>
      ) : !isSupported() ? (
        <p role="alert" className="text-critical-text mt-3 text-sm">
          This browser has no passkey support, so it cannot register one. Safari, Chrome, Edge and
          Firefox all support passkeys on current versions.
        </p>
      ) : (
        <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
          <p className="text-ink-secondary text-sm">
            Register a passkey on this device. There is no password to choose — the passkey stays on
            this device and is how you sign in from now on.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={redeem}
            className="bg-accent-bg text-accent-strong mt-4 w-full rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Waiting for your device…" : "Register a passkey"}
          </button>

          {name ? (
            <p role="status" className="text-ink-secondary mt-3 text-sm">
              Welcome, {name}. Taking you to the dashboard.
            </p>
          ) : null}

          {error ? (
            <p role="alert" className="text-critical-text mt-3 text-sm">
              {error}
            </p>
          ) : null}

          <p className="text-ink-muted mt-4 text-xs">
            An invitation works once and expires. If it has already been used, or has expired, ask
            for a new one.
          </p>
        </div>
      )}
    </div>
  );
}
