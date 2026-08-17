# syntax=docker/dockerfile:1
#
# This image ships to Fly (ticket 008). The `dev` stage exists for the compose
# override's hot reload; `runtime` is what deploys.

FROM node:22-alpine AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    CI=true
RUN corepack enable
WORKDIR /app

# ── dependencies, isolated (pnpm's default) ───────────────────────────────────
# Feeds the dev stage, which runs `next dev` and never produces standalone output,
# so it has no reason to diverge from a developer's own node_modules.
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── dependencies, hoisted ─────────────────────────────────────────────────────
# Feeds the production build only.
#
# Next.js standalone tracing cannot follow pnpm's symlinked store: it copies next/
# but misses transitive internals like @swc/helpers, and server.js dies at startup
# with MODULE_NOT_FOUND. A flat layout is the fix.
#
# Appended here rather than committed to pnpm-workspace.yaml for two reasons: pnpm 11
# accepts the setting from that file alone (the --node-linker flag is gone and .npmrc
# is no longer read for it), and pnpm only relayouts a node_modules built from
# scratch — always true in this stage, never true on a dev machine.
FROM base AS deps-hoisted
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN printf '\nnodeLinker: hoisted\n' >> pnpm-workspace.yaml
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── dev (compose override only, never deployed) ───────────────────────────────
FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# ── builder ───────────────────────────────────────────────────────────────────
FROM base AS builder
COPY --from=deps-hoisted /app/node_modules ./node_modules
COPY . .
# COPY brought back the committed pnpm-workspace.yaml; re-append so the config and
# the installed layout agree and pnpm doesn't try to purge node_modules mid-build.
RUN printf '\nnodeLinker: hoisted\n' >> pnpm-workspace.yaml
RUN pnpm build

# ── runtime ───────────────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs

# Standalone output carries its own minimal node_modules and server.js. It does
# not include public/ or .next/static — those are copied deliberately, and
# server.js serves them once they are in place.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=12 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
