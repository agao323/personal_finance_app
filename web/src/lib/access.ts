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
import { createRemoteJWKSet, decodeJwt, jwtVerify } from "jose";

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
  /**
   * True when an assertion was supplied and failed to verify, as opposed to none
   * being supplied at all.
   *
   * The difference is what makes recovery possible: a token that failed is a *stuck*
   * session and deleting it is the fix, while no token is an ordinary refusal with
   * nothing to delete.
   */
  hadAssertion?: boolean;
}

/**
 * What the token *claimed*, for the log line only.
 *
 * Decoded without verifying, which is safe precisely because nothing acts on it — it
 * exists so "unexpected iss claim value" can say which value, rather than sending
 * someone to compare two dashboards. Only `iss` and `aud` are read: both already
 * appear in every Access redirect URL, so neither is a disclosure. The identity
 * claims are deliberately left alone.
 */
function claimedBy(token: string): string {
  try {
    const payload = decodeJwt(token);
    return ` [token iss=${String(payload.iss)} aud=${JSON.stringify(payload.aud)}]`;
  } catch {
    return " [token could not be decoded]";
  }
}

export async function verifyAccessJwt(
  token: string | undefined,
  config: AccessConfig,
): Promise<AccessResult> {
  if (!token) return { ok: false, reason: "no Access assertion", hadAssertion: false };

  try {
    const { payload } = await jwtVerify(token, keysFor(config), {
      issuer: `https://${config.teamDomain}`,
      audience: config.audience,
    });
    return { ok: true, email: typeof payload.email === "string" ? payload.email : undefined };
  } catch (cause: unknown) {
    const why = cause instanceof Error ? cause.message : "invalid assertion";
    return { ok: false, reason: why + claimedBy(token), hadAssertion: true };
  }
}

export function assertionFrom(headers: Headers): string | undefined {
  return headers.get(HEADER) ?? undefined;
}
