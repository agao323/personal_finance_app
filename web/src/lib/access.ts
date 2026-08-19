/**
 * Cloudflare Access JWT validation.
 *
 * **Defense in depth, not the gate.** Access refuses unauthorised identities at the
 * edge, so in normal operation nothing that fails this check ever reaches the origin.
 * This exists for the case where the Fly app is given a public address by accident —
 * which is a one-line mistake in a config file, and otherwise a silent one.
 *
 * Verified against Cloudflare's published keys rather than merely decoded. A JWT that
 * is only decoded is a header anyone can write; checking the signature, the issuer,
 * and the audience is what makes it evidence of anything.
 *
 * Disabled when unconfigured, so local development and the demo — neither of which
 * sits behind Access — do not need a team domain to run. The deployment sets both
 * variables, and `isEnforced` is what a startup check can assert on.
 */
import { createRemoteJWKSet, jwtVerify } from "jose";

const HEADER = "cf-access-jwt-assertion";

export interface AccessConfig {
  teamDomain: string;
  audience: string;
}

export function readConfig(env: Record<string, string | undefined>): AccessConfig | null {
  const teamDomain = env.CF_ACCESS_TEAM_DOMAIN;
  const audience = env.CF_ACCESS_AUD;
  if (!teamDomain || !audience) return null;
  return { teamDomain: teamDomain.replace(/^https?:\/\//, "").replace(/\/$/, ""), audience };
}

export function isEnforced(env: Record<string, string | undefined>): boolean {
  return readConfig(env) !== null;
}

/** Cached across requests — refetching Cloudflare's keys on every request is a DoS on yourself. */
const keySets = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function keysFor(config: AccessConfig) {
  const url = `https://${config.teamDomain}/cdn-cgi/access/certs`;
  let keys = keySets.get(url);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(url));
    keySets.set(url, keys);
  }
  return keys;
}

export interface AccessResult {
  ok: boolean;
  reason?: string;
  email?: string;
}

export async function verifyAccessJwt(
  token: string | undefined,
  config: AccessConfig,
): Promise<AccessResult> {
  if (!token) return { ok: false, reason: "no Access assertion" };

  try {
    const { payload } = await jwtVerify(token, keysFor(config), {
      issuer: `https://${config.teamDomain}`,
      audience: config.audience,
    });
    return { ok: true, email: typeof payload.email === "string" ? payload.email : undefined };
  } catch (cause: unknown) {
    return { ok: false, reason: cause instanceof Error ? cause.message : "invalid assertion" };
  }
}

export function assertionFrom(headers: Headers): string | undefined {
  return headers.get(HEADER) ?? undefined;
}
