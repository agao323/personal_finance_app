"use client";

/**
 * Sign in, or register this device's first passkey.
 *
 * One page for both because they are the same decision from the reader's side — "let
 * me in on this device" — and splitting them means guessing which one a visitor
 * needs. Registration is available because the API allows it while no passkey exists
 * yet, and behind Cloudflare Access on the real deployment; if a passkey does exist,
 * the API refuses and the message says so.
 *
 * No password field exists anywhere in this app, and there is no fallback to add one
 * to. See docs/SECURITY.md#auth.
 */

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

import { Skeleton } from "@/components/states";
import { apiFetch } from "@/lib/api";
import { createCredential, getCredential, isSupported } from "@/lib/webauthn";

export default function LoginPage() {
  return (
    <Suspense fallback={<Skeleton className="h-48 w-full max-w-md" />}>
      <LoginScreen />
    </Suspense>
  );
}

type Mode = "signin" | "register";

/**
 * Where to go after signing in, refusing anything off-site.
 *
 * An open redirect on a sign-in page is how a phishing link borrows your domain: the
 * URL is genuinely yours, the sign-in is genuinely yours, and the landing page is
 * theirs. A leading `//` is the case a naive `startsWith("/")` check misses —
 * `//evil.example` is a protocol-relative URL, not a path.
 */
export function safeNext(next: string): string {
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  return next;
}

export function LoginScreen() {
  const search = useSearchParams();
  const next = search?.get("next") ?? "/";
  const expired = search?.get("expired") === "1";

  const [busy, setBusy] = useState<Mode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const supported = isSupported();

  async function run(mode: Mode) {
    setBusy(mode);
    setError(null);
    try {
      if (mode === "signin") {
        const started = await apiFetch("/auth/login/options", { method: "post" });
        const credential = await getCredential(started.options);
        await apiFetch("/auth/login/verify", {
          method: "post",
          body: { challenge_id: started.challenge_id, credential },
        });
      } else {
        const started = await apiFetch("/auth/register/options", { method: "post" });
        const credential = await createCredential(started.options);
        await apiFetch("/auth/register/verify", {
          method: "post",
          body: { challenge_id: started.challenge_id, credential },
        });
      }
      // A full navigation, not a client-side push: the session cookie was just set
      // and every cached server render was produced without it.
      globalThis.location.assign(safeNext(next));
    } catch (cause: unknown) {
      // A cancelled Touch ID prompt throws too. It is not a failure worth a red
      // banner, but it is worth saying nothing happened.
      const message =
        cause instanceof Error && cause.name === "NotAllowedError"
          ? "That was cancelled — nothing has changed."
          : cause instanceof Error
            ? cause.message
            : "Something went wrong.";
      setError(message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-xl font-medium tracking-tight">Sign in</h1>

      {expired ? (
        <p className="text-ink-secondary mt-2 text-sm">
          Your session ended. Sign in again to carry on.
        </p>
      ) : (
        <p className="text-ink-secondary mt-2 text-sm">
          This app uses passkeys. There is no password to type, forget, or have stolen.
        </p>
      )}

      {!supported ? (
        <p role="alert" className="text-critical-text mt-4 text-sm">
          This browser has no passkey support, so there is no way to sign in from it. Safari,
          Chrome, Edge and Firefox all support passkeys on current versions.
        </p>
      ) : (
        <div className="border-hairline bg-surface-1 mt-4 rounded-xl border p-4">
          <button
            type="button"
            onClick={() => run("signin")}
            disabled={busy !== null}
            className="bg-accent-bg text-accent-strong w-full rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy === "signin" ? "Waiting for your passkey…" : "Sign in with a passkey"}
          </button>

          <p className="text-ink-muted mt-4 text-xs">
            First time on this household&rsquo;s account? Register a passkey. This only works until
            the first one exists — after that, sign in with a device you already registered.
          </p>
          <button
            type="button"
            onClick={() => run("register")}
            disabled={busy !== null}
            className="border-hairline hover:bg-surface-2 mt-2 w-full rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50"
          >
            {busy === "register" ? "Waiting for your device…" : "Register a passkey"}
          </button>

          {error ? (
            <p role="alert" className="text-critical-text mt-3 text-sm">
              {error}
            </p>
          ) : null}
        </div>
      )}

      {supported ? (
        <p className="text-ink-secondary mt-4 text-sm">
          Lost the device with your passkey?{" "}
          <Link href="/recover" className="text-accent underline underline-offset-4">
            Register a replacement
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
