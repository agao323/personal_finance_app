"use client";

/**
 * Who you are, and how to stop being signed in.
 *
 * Both of the endpoints behind this existed for a while with nothing calling them.
 * With one household member "whose numbers are these" reads as a question nobody
 * needed to ask; the moment a second person exists it is the first one.
 *
 * **Two sign-out actions, not one.** The application session and the Cloudflare Access
 * session are independent, and collapsing them would be wrong in both directions: one
 * button that ended only the app session would leave a "signed out" state where Access
 * still waves you through, and one that always ended both would make the ordinary case
 * — lock this app on my own laptop — cost a full Access round trip to undo.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { IS_DEMO } from "@/lib/demo";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";

type SessionRead = ResponseOf<"/auth/session", "get">;

export function AccountMenu() {
  const [session, setSession] = useState<SessionRead | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // The demo has no accounts and no session to read.
    if (IS_DEMO) return;
    let live = true;
    apiFetch("/auth/session")
      .then((data) => {
        if (live) setSession(data);
      })
      .catch(() => {
        // Not signed in, or the session just ended. The expiry bar handles saying so;
        // this control simply has nothing to show.
        if (live) setSession(null);
      });
    return () => {
      live = false;
    };
  }, []);

  if (IS_DEMO || !session) return null;

  async function signOut(alsoAccess: boolean) {
    setBusy(true);
    try {
      await apiFetch("/auth/logout", { method: "post" });
    } catch {
      // Clearing the cookie is the server's job and it may already be gone. Either
      // way the next step is the same, and refusing to navigate because logout
      // returned an error would strand someone trying to leave.
    }
    // Full navigation, never a client-side push: every cached render was produced
    // with a session that no longer exists.
    globalThis.location.assign(alsoAccess ? "/cdn-cgi/access/logout" : "/login");
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
        className="text-ink-secondary hover:text-ink flex items-center gap-1.5 px-3 py-3 text-sm whitespace-nowrap"
      >
        {session.display_name}
        <span aria-hidden="true" className="text-xs">
          ▾
        </span>
      </button>

      {open ? (
        <>
          {/* Click-away. A menu that only closes by pressing its own button is a
              menu people leave open. */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-10 cursor-default"
          />
          <div
            role="menu"
            className="border-hairline bg-surface-2 absolute right-0 z-20 mt-1 w-64 rounded-xl border p-1 shadow-lg"
          >
            <p className="text-ink-muted px-3 py-2 text-xs break-all">{session.email}</p>

            <Link
              role="menuitem"
              href="/settings/passkeys"
              onClick={() => setOpen(false)}
              className="hover:bg-surface-1 block rounded-lg px-3 py-2 text-sm"
            >
              Passkeys
            </Link>

            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => signOut(false)}
              className="hover:bg-surface-1 block w-full rounded-lg px-3 py-2 text-left text-sm disabled:opacity-50"
            >
              Sign out
            </button>

            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => signOut(true)}
              className="hover:bg-surface-1 text-ink-secondary block w-full rounded-lg px-3 py-2 text-left text-sm disabled:opacity-50"
            >
              Sign out of Access too
              <span className="text-ink-muted mt-0.5 block text-xs">
                For a shared or borrowed machine.
              </span>
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
