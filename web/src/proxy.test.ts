import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { isEnforced, readConfig, verifyAccessJwt } from "@/lib/access";
import { proxy } from "@/proxy";

describe("Cloudflare Access configuration", () => {
  it("is disabled when unconfigured, so local dev and the demo still run", () => {
    expect(isEnforced({})).toBe(false);
    expect(isEnforced({ CF_ACCESS_TEAM_DOMAIN: "acme.cloudflareaccess.com" })).toBe(false);
  });

  it("is enforced once both the team domain and the audience are set", () => {
    // Both: an audience without an issuer accepts a token from any Access tenant,
    // and an issuer without an audience accepts one minted for a different app.
    expect(
      isEnforced({ CF_ACCESS_TEAM_DOMAIN: "acme.cloudflareaccess.com", CF_ACCESS_AUD: "abc123" }),
    ).toBe(true);
  });

  it("normalises a team domain given as a URL", () => {
    const config = readConfig({
      CF_ACCESS_TEAM_DOMAIN: "https://acme.cloudflareaccess.com/",
      CF_ACCESS_AUD: "abc123",
    });

    expect(config?.teamDomain).toBe("acme.cloudflareaccess.com");
  });

  it("refuses a request with no assertion at all", async () => {
    const result = await verifyAccessJwt(undefined, {
      teamDomain: "acme.cloudflareaccess.com",
      audience: "abc123",
    });

    expect(result.ok).toBe(false);
    expect(result.reason).toMatch(/no Access assertion/);
  });

  it("refuses a token it cannot verify rather than decoding and trusting it", async () => {
    // A decoded-but-unverified JWT is a header anyone can write.
    const result = await verifyAccessJwt("not.a.jwt", {
      teamDomain: "acme.cloudflareaccess.com",
      audience: "abc123",
    });

    expect(result.ok).toBe(false);
  });
});

describe("the health path", () => {
  it("passes straight through, so Fly can check a machine nobody has signed into", async () => {
    const response = await proxy(new NextRequest("http://localhost:3000/healthz"));

    expect(response.status).toBe(200);
  });

  it("answers the prober even with Access configured and no assertion", async () => {
    // Fly's prober runs inside the machine and never carries an Access assertion.
    // Checking Access first returns 403 to it, both machines go critical, and
    // deploys time out waiting for health — which is exactly what happened.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const response = await proxy(new NextRequest("http://localhost:3000/healthz"));

    expect(response.status).not.toBe(403);
    vi.unstubAllEnvs();
  });

  it("still refuses an ordinary path that did not pass Access", async () => {
    // The exemption is for the probe alone. Everything else arrives through the
    // edge and must prove it got there legitimately.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const response = await proxy(new NextRequest("http://localhost:3000/accounts"));

    expect(response.status).toBe(403);
    vi.unstubAllEnvs();
  });
});

describe("rejection diagnostics", () => {
  it("names the issuer the token claimed, not just the one expected", async () => {
    // "unexpected iss claim value" without the value sends you comparing dashboards.
    // Decoded without verifying, because nothing acts on it — iss and aud already
    // appear in every Access redirect URL.
    const header = Buffer.from(JSON.stringify({ alg: "RS256" })).toString("base64url");
    const body = Buffer.from(
      JSON.stringify({ iss: "https://old-team.cloudflareaccess.com", aud: ["abc"] }),
    ).toString("base64url");

    const result = await verifyAccessJwt(`${header}.${body}.sig`, {
      teamDomain: "new-team.cloudflareaccess.com",
      audience: "abc",
    });

    expect(result.ok).toBe(false);
    expect(result.reason).toContain("old-team.cloudflareaccess.com");
  });

  it("says so when the token is not a JWT at all", async () => {
    const result = await verifyAccessJwt("garbage", {
      teamDomain: "t.cloudflareaccess.com",
      audience: "abc",
    });

    expect(result.reason).toContain("could not be decoded");
  });
});

/** A syntactically valid JWT with the given claims. The signature is nonsense. */
function fakeToken(claims: Record<string, unknown>): string {
  const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${part({ alg: "RS256" })}.${part(claims)}.sig`;
}

describe("recovering from a stuck Access session", () => {
  it("clears the cookie when an assertion was supplied and failed", async () => {
    // Every other escape hatch reads the very value that is broken: Cloudflare's own
    // logout could not resolve an org out of the stale cookie, and the team-domain
    // logout does not touch this cookie at all. This origin serves the hostname the
    // cookie is set on, so it can simply delete it.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "new-team.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");
    const request = new NextRequest("http://localhost:3000/");
    request.headers.set(
      "cf-access-jwt-assertion",
      fakeToken({ iss: "https://old-team.cloudflareaccess.com", aud: ["abc123"] }),
    );

    const response = await proxy(request);

    expect(response.status).toBe(403);
    expect(response.cookies.get("CF_Authorization")?.value).toBe("");
    vi.unstubAllEnvs();
  });

  it("does not clear anything when no assertion was supplied", async () => {
    // Nothing to clear, and that case is an ordinary refusal rather than a stuck
    // session — a visitor who never authenticated should not be handed a Set-Cookie.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "new-team.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const response = await proxy(new NextRequest("http://localhost:3000/"));

    expect(response.status).toBe(403);
    expect(response.cookies.get("CF_Authorization")).toBeUndefined();
    vi.unstubAllEnvs();
  });

  it("tells the reader to reload once the session has been cleared", async () => {
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "new-team.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");
    const request = new NextRequest("http://localhost:3000/");
    request.headers.set(
      "cf-access-jwt-assertion",
      fakeToken({ iss: "https://old-team.cloudflareaccess.com", aud: ["abc123"] }),
    );

    const body = await (await proxy(request)).text();

    expect(body).toContain("Reload the page");
    // And says what a repeat means, so a configuration error is not mistaken for a
    // stuck session forever.
    expect(body).toContain("configuration rather than");
    vi.unstubAllEnvs();
  });

  it("never redirects, because a configuration error would loop", async () => {
    // clear → Access → fresh token → rejected → clear, and the browser never stops.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "new-team.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");
    const request = new NextRequest("http://localhost:3000/");
    request.headers.set("cf-access-jwt-assertion", fakeToken({ iss: "https://x", aud: ["y"] }));

    const response = await proxy(request);

    expect(response.status).toBe(403);
    expect(response.headers.get("location")).toBeNull();
    vi.unstubAllEnvs();
  });
});

describe("the forbidden page", () => {
  it("tells a visitor with no assertion to sign in", async () => {
    // Not "clear your cookies" — there is nothing to clear, and advice that does not
    // apply is worse than none. The stuck-session case gets its own wording above.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const body = await (await proxy(new NextRequest("http://localhost:3000/"))).text();

    expect(body).toContain("Sign in through Cloudflare Access");
    expect(body).not.toContain("Reload the page");
    vi.unstubAllEnvs();
  });

  it("does not say which check failed", async () => {
    // That belongs in the log, where only the operator reads it.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const body = await (await proxy(new NextRequest("http://localhost:3000/"))).text();

    expect(body).not.toContain("example.cloudflareaccess.com");
    expect(body).not.toContain("abc123");
    expect(body.toLowerCase()).not.toContain("iss");
    vi.unstubAllEnvs();
  });
});
