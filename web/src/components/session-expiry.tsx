"use client";

/**
 * The re-authentication prompt.
 *
 * A 401 mid-session is not an error to render in a panel — nothing is broken, the
 * session simply ended. Showing "Could not load this" for it sends the reader
 * debugging their network, and a silent redirect throws away whatever they were
 * partway through typing.
 *
 * So: a bar, an explanation, and one button. Everything on screen stays where it is.
 */

import { useEffect, useState } from "react";

import { SESSION_EXPIRED_EVENT } from "@/lib/api";
import { IS_DEMO } from "@/lib/demo";

export function SessionExpiry() {
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    // The demo has no sessions to expire, and its bundle has no sign-in page to
    // send anyone to.
    if (IS_DEMO) return;
    const onExpired = () => setExpired(true);
    globalThis.addEventListener?.(SESSION_EXPIRED_EVENT, onExpired);
    return () => globalThis.removeEventListener?.(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  if (!expired) return null;

  return (
    <div
      role="alert"
      className="border-warning/40 bg-surface-1 sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2 text-sm"
    >
      <span>Your session ended. Anything on screen may be out of date.</span>
      <a
        href={`/login?next=${encodeURIComponent(globalThis.location?.pathname ?? "/")}`}
        className="border-hairline hover:bg-surface-2 rounded-lg border px-3 py-1 transition-colors"
      >
        Sign in again
      </a>
    </div>
  );
}
