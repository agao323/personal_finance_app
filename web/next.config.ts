import type { NextConfig } from "next";

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
        ],
      },
    ];
  },
};

export default nextConfig;
