"use client";

/**
 * Who you are, and how to stop being signed in.
 *
 * **One sign-out, because there is only one session.** Ticket 041 built two — the
 * application's own and Cloudflare's — and argued that collapsing them would be wrong in
 * both directions. 047b removed the application session entirely, so the argument no
 * longer has two sides: Cloudflare's is the only session, and only Cloudflare can end it.
 *
 * That logout is served by the edge, and it is worth knowing it fails when the Access
 * organisation named in the cookie no longer resolves — which is exactly when somebody
 * most needs it. The recovery for that case is `proxy.ts` clearing `CF_Authorization`
 * from the origin on a failed assertion (ticket 042), not this button.
 */

import { useEffect, useState } from "react";

import { IS_DEMO } from "@/lib/demo";
import type { ResponseOf } from "@/lib/api";
import { apiFetch } from "@/lib/api";

type SessionRead = ResponseOf<"/auth/session", "get">;

/** Cloudflare's own logout, on this hostname. Not a route this app serves. */
const ACCESS_LOGOUT = "/cdn-cgi/access/logout";

export function AccountMenu() {
  const [session, setSession] = useState<SessionRead | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    // The demo has no accounts and no session to read.
    if (IS_DEMO) return;
    let live = true;
    apiFetch("/auth/session")
      .then((data) => {
        if (live) setSession(data);
      })
      .catch(() => {
        // Nothing to show. A request that gets this far has already passed Access, so
        // a failure here is the app's own refusal — an identity Access authenticated
        // that this household never added, or one since deactivated — and the answer
        // is an absent control rather than a banner about a session that never existed.
        if (live) setSession(null);
      });
    return () => {
      live = false;
    };
  }, []);

  if (IS_DEMO || !session) return null;

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

            {/* A plain link, not a fetch. This is Cloudflare's endpoint on this
                hostname and the browser has to follow it for the redirect to land. */}
            <a
              role="menuitem"
              href={ACCESS_LOGOUT}
              className="hover:bg-surface-1 block rounded-lg px-3 py-2 text-sm"
            >
              Sign out
              <span className="text-ink-muted mt-0.5 block text-xs">
                Ends your Cloudflare Access session.
              </span>
            </a>
          </div>
        </>
      ) : null}
    </div>
  );
}
