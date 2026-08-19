import { NextResponse, type NextRequest } from "next/server";

import { IS_DEMO } from "@/lib/demo";

/**
 * Send unauthenticated visitors to the sign-in page.
 *
 * Named `proxy.ts` because Next 16 deprecated the `middleware` file convention and
 * renamed it. Confusingly this app already has something it calls "the proxy" — the
 * `/api/[...path]` route handler that forwards to the private API. They are unrelated:
 * that one is the request path, this one is a redirect that runs before rendering.
 *
 * This is a **convenience, not the security boundary**. It checks only that a session
 * cookie is present — it cannot verify the signature, because the secret lives in the
 * API and putting it in the edge runtime would be a second copy of the one thing that
 * must not leak. Every request that matters is authenticated again by the API, and on
 * the real deployment Cloudflare Access has already refused anyone who does not
 * belong before this code runs at all.
 *
 * What it buys is that an expired session lands on a sign-in page instead of a
 * dashboard full of error panels.
 */
const SESSION_COOKIE = "pfa_session";

/** Paths that must stay reachable without a session. */
const PUBLIC_PREFIXES = ["/login"];

export function isPublicPath(pathname: string): boolean {
  // Every `/api/*` path is exempt, not just the auth ones. Redirecting a `fetch` to
  // the sign-in page answers it with a 200 and an HTML body, which the caller parses
  // as JSON and reports as a mystery. An expired session has to come back as a real
  // 401 so the app can say "your session ended" — that is the thing the BFF topology
  // buys, and throwing it away here would be a waste of it.
  if (pathname.startsWith("/api/")) return true;
  // Exact match, or the prefix followed by a separator. A bare `startsWith` would
  // make `/loginsomething` public, which is a way to accidentally expose a route by
  // naming it badly.
  return PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function proxy(request: NextRequest) {
  // The demo has no accounts to sign in to, and its bundle contains no sign-in path.
  if (IS_DEMO) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  if (isPublicPath(pathname)) return NextResponse.next();
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  // Where they were going, so signing in does not dump them on the dashboard.
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
