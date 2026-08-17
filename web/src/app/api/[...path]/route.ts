/**
 * Server-side proxy to the FastAPI service.
 *
 * This handler is the entire reason there is no CORS config, no second Cloudflare
 * Access application, and no public address on the API. The browser talks only to
 * this origin; this code is the only thing that knows where the API lives.
 *
 * See docs/ARCHITECTURE.md#request-path.
 */

import type { NextRequest } from "next/server";

/**
 * Hop-by-hop headers are meaningful only for a single transport connection and must
 * not be forwarded by an intermediary (RFC 9110 §7.6.1). Forwarding `connection` or
 * `transfer-encoding` produces responses that are subtly corrupt in ways that are
 * miserable to debug.
 */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

/** Also dropped: `host` would announce this origin, and `content-length` is recomputed. */
const NEVER_FORWARD = new Set([...HOP_BY_HOP, "host", "content-length"]);

function forwardableHeaders(headers: Headers): Headers {
  const result = new Headers();
  headers.forEach((value, key) => {
    if (!NEVER_FORWARD.has(key.toLowerCase())) result.append(key, value);
  });
  return result;
}

function targetUrl(request: NextRequest, segments: string[]): string {
  const base = process.env.INTERNAL_API_URL;
  if (!base) {
    throw new Error(
      "INTERNAL_API_URL is not set. The proxy has no API to forward to — see .env.example.",
    );
  }
  const { search } = new URL(request.url);
  return `${base.replace(/\/$/, "")}/${segments.map(encodeURIComponent).join("/")}${search}`;
}

async function proxy(
  request: NextRequest,
  context: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await context.params;

  let url: string;
  try {
    url = targetUrl(request, path);
  } catch (error) {
    return Response.json(
      { detail: error instanceof Error ? error.message : "Proxy misconfigured" },
      { status: 500 },
    );
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers: forwardableHeaders(request.headers),
      body: hasBody ? request.body : undefined,
      // Required by undici when streaming a request body rather than buffering it.
      ...(hasBody ? { duplex: "half" } : {}),
      redirect: "manual",
      cache: "no-store",
    } as RequestInit);
  } catch {
    // The API being unreachable is a gateway failure, not a client error. Returning
    // 502 keeps it distinguishable from anything the API itself would have said.
    return Response.json({ detail: "Upstream API unreachable" }, { status: 502 });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: forwardableHeaders(upstream.headers),
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;

// A proxy must never be statically optimised or cached.
export const dynamic = "force-dynamic";
