"use client";

/**
 * Recover an account whose passkey is gone.
 *
 * Reachable without a session, because the person who needs it cannot produce one —
 * that is the definition of the problem. Cloudflare Access has already established who
 * they are before this page loads, and the API verifies that assertion itself before
 * registering anything.
 *
 * This is what ADR 0002 always described: "a lost passkey is recovered by
 * re-registering from behind Access". It went unimplemented for a while, during which
 * losing a single device meant a permanent lockout with no way back from inside the
 * app — the guard against removing your last passkey existed, and the door back did
 * not.
 */

import { useState } from "react";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { createCredential, isSupported } from "@/lib/webauthn";

export default function RecoverPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function recover() {
    setBusy(true);
    setError(null);
    try {
      const started = await apiFetch("/auth/recover/options", { method: "post" });
      const credential = await createCredential(started.options);
      await apiFetch("/auth/recover/verify", {
        method: "post",
        body: { challenge_id: started.challenge_id, credential },
      });
      // Full navigation: the session cookie was just set.
      globalThis.location.assign("/");
    } catch (cause: unknown) {
      setError(
        cause instanceof Error && cause.name === "NotAllowedError"
          ? "That was cancelled — nothing has changed."
          : cause instanceof Error
            ? cause.message
            : "That did not work.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-md">
      <h1 className="text-xl font-medium tracking-tight">Register a replacement passkey</h1>
      <p className="text-ink-secondary mt-2 text-sm">
        Lost the device you used to sign in? You have already proved who you are to Cloudflare
        Access to reach this page, so you can register a new passkey on this device.
      </p>

      {!isSupported() ? (
        <p role="alert" className="text-critical-text mt-4 text-sm">
          This browser has no passkey support, so it cannot register one. Try Safari, Chrome, Edge
          or Firefox.
        </p>
      ) : (
        <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
          <button
            type="button"
            disabled={busy}
            onClick={recover}
            className="bg-accent-bg text-accent-strong w-full rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Waiting for your device…" : "Register a passkey on this device"}
          </button>

          {error ? (
            <p role="alert" className="text-critical-text mt-3 text-sm">
              {error}
            </p>
          ) : null}

          <p className="text-ink-muted mt-4 text-xs">
            Your old passkeys are left alone — a phone that turns up in a coat pocket still works.
            Remove anything genuinely gone from the passkeys screen once you are back in.
          </p>
        </div>
      )}

      <p className="text-ink-secondary mt-4 text-sm">
        Still have your device?{" "}
        <Link href="/login" className="text-accent underline underline-offset-4">
          Sign in normally
        </Link>
        .
      </p>
    </div>
  );
}
