import { NextResponse, type NextRequest } from "next/server";

import { assertionFrom, readConfig, verifyAccessJwt } from "@/lib/access";
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

/**
 * What an unauthenticated visitor sees instead of a bare "Forbidden".
 *
 * Deliberately says nothing about *which* check failed or what was expected — that
 * belongs in the log, where only the operator can read it. What it does say is the one
 * thing a legitimate person locked out needs to know, because a stale session and a
 * genuine refusal look identical from here and the bare word "Forbidden" sends you
 * nowhere. It cost hours the first time.
 *
 * No new information for an attacker: the edge already redirects to a Cloudflare
 * Access login page, so "this site uses Access" is not a secret.
 */
const ACCESS_COOKIE = "CF_Authorization";

const forbiddenPage = (cleared: boolean): string => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forbidden</title>
<style>
  :root { color-scheme: light dark }
  body { font: 16px/1.6 system-ui, sans-serif; max-width: 34rem; margin: 12vh auto; padding: 0 1.5rem }
  h1 { font-size: 1.25rem; margin: 0 0 .75rem }
  p { margin: 0 0 1rem }
  code { font-size: .9em }
</style></head><body>
<h1>Forbidden</h1>
<p>This request did not pass Cloudflare Access.</p>
${
  cleared
    ? `<p>Your sign-in for this site has been cleared, because it could not be verified.
<strong>Reload the page</strong> to sign in again.</p>
<p>If reloading brings you straight back here, the problem is configuration rather than
your session — the server log says which check failed.</p>`
    : `<p>Sign in through Cloudflare Access and try again.</p>`
}
</body></html>`;

/** Fly's liveness probe. Exempt from both the Access check and the auth redirect. */
const HEALTH_PATH = "/healthz";

/** Paths that must stay reachable without a session. */
const PUBLIC_PREFIXES = [
  "/login",
  // Redeeming an invitation cannot require a session: the person opening it does not
  // have one yet, which is the entire point. They have already passed Access to reach
  // it, and the token is single-use and expiring.
  "/invitation",
  // Recovery is for somebody who cannot produce a session — that is the definition of
  // the problem it solves. Cloudflare Access has already identified them, and the API
  // verifies that assertion itself before registering anything.
  "/recover",
  HEALTH_PATH,
];

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

export async function proxy(request: NextRequest) {
  // The demo has no accounts to sign in to, and its bundle contains no sign-in path.
  if (IS_DEMO) return NextResponse.next();

  // Liveness first, before the Access check. Fly's health prober runs *inside* the
  // machine and therefore never carries an Access assertion — so with Access
  // configured, checking it first returns 403 to the prober, both machines go
  // critical, and deploys start timing out on health. That happened.
  //
  // Safe to exempt: it returns `{"status":"ok"}` and nothing else, and it is only
  // reachable on the internal port. Nothing else gets this treatment — `/api/*`
  // arrives through the edge and must still prove it passed Access.
  if (request.nextUrl.pathname === HEALTH_PATH) return NextResponse.next();

  // Cloudflare Access, when configured. Nothing that fails this should ever arrive —
  // Access refuses it at the edge — so a failure here means the origin was reached
  // directly, which is the accident this check exists to catch. 403, not a redirect:
  // there is no sign-in this origin can offer that would help.
  const access = readConfig(process.env);
  if (access) {
    const verified = await verifyAccessJwt(assertionFrom(request.headers), access);
    if (!verified.ok) {
      // The reason goes to the log, never to the response. A misconfigured team
      // domain rejects *everyone* — the keys cannot be fetched, so every assertion
      // fails — and a bare 403 gives whoever is locked out nothing to go on. It also
      // must not tell an attacker which part of the check they failed.
      console.error(`[access] rejected: ${verified.reason} (issuer https://${access.teamDomain})`);
      const response = new NextResponse(forbiddenPage(verified.hadAssertion === true), {
        status: 403,
        headers: { "content-type": "text/html; charset=utf-8" },
      });

      if (verified.hadAssertion) {
        // Delete the stuck token. This origin serves the same hostname Cloudflare
        // set the cookie on, so it is ours to clear — which matters because every
        // other escape hatch reads the very value that is broken: Cloudflare's own
        // logout could not resolve an organisation out of a stale cookie, and the
        // team-domain logout does not touch this cookie at all.
        //
        // Deliberately no redirect. If the rejection is a configuration error rather
        // than a stale token, clear → Access → fresh token → rejected would loop and
        // the browser would never stop. A reload the reader chooses cannot.
        response.cookies.set(ACCESS_COOKIE, "", { maxAge: 0, path: "/" });
      }

      return response;
    }
  }

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
