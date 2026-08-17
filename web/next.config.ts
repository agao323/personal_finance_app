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
};

export default nextConfig;
