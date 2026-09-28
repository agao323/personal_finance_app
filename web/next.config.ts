import type { NextConfig } from "next";

/**
 * The content security policy, as directives. Exported for the test that checks it.
 *
 * The third of three layers against exfiltration through the browser (docs/ADVISOR.md
 * #prompt-injection): the API strips images and links from answers, the renderer has no way
 * to draw one, and this makes the browser refuse to fetch anything that got past both.
 *
 * - `img-src` and `connect-src` are this origin only. Every API call already goes through
 *   the same-origin proxy, and Sentry reports from the server, so nothing else is needed —
 *   and `'self'` stays trustworthy only because nothing on this origin redirects elsewhere
 *   (the proxy refuses upstream redirects; the API has none).
 * - `frame-ancestors 'none'` is the CSP form of `X-Frame-Options: DENY`.
 * - **`script-src` is not tightened here.** Next's inline scripts need per-request nonces,
 *   which is its own piece of work; with no `default-src`, scripts are unrestricted as before.
 */
export const CSP_DIRECTIVES: Record<string, string> = {
  "img-src": "'self' data: blob:",
  "connect-src": "'self'",
  "frame-ancestors": "'none'",
  "object-src": "'none'",
  "base-uri": "'self'",
  "form-action": "'self'",
};

export const CONTENT_SECURITY_POLICY = Object.entries(CSP_DIRECTIVES)
  .map(([directive, value]) => `${directive} ${value}`)
  .join("; ");

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js, so the runtime image
  // carries only traced dependencies instead of the full node_modules. See
  // web/Dockerfile — public/ and .next/static are copied in separately.
  output: "standalone",

  // Tracing misses @swc/helpers under pnpm: next's require-hook resolves it from
  // inside next's own store directory, and standalone copies the package to the
  // top level and to .pnpm/node_modules but not there, so server.js dies at startup
  // with MODULE_NOT_FOUND. Force the whole package in — it is ~50KB.
  outputFileTracingIncludes: {
    "/**": ["./node_modules/.pnpm/**/@swc/helpers/**"],
  },

  /**
   * Security headers on every response.
   *
   * HSTS is set at the origin as well as at Cloudflare: an origin that only relies on
   * the edge for it is one misrouted request away from serving plain HTTP, and the
   * header costs nothing. Two years with `includeSubDomains` so the demo hostname is
   * covered by the same commitment.
   *
   * `noindex` is belt and braces alongside the `robots` metadata in the layout. The
   * demo overrides it (ticket 037) — it is meant to be indexed; the real app never is,
   * and a header is harder to lose in a refactor than a metadata export.
   */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "X-Robots-Tag",
            value: process.env.NEXT_PUBLIC_DEMO === "true" ? "all" : "noindex, nofollow",
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // No third-party embeds anywhere in this app, so the strictest value is
          // also the correct one.
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: CONTENT_SECURITY_POLICY },
        ],
      },
    ];
  },
};

export default nextConfig;
