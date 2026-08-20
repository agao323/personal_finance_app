import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { isEnforced, readConfig, verifyAccessJwt } from "@/lib/access";
import { isPublicPath, proxy } from "@/proxy";

describe("isPublicPath", () => {
  it("lets the sign-in page through", () => {
    expect(isPublicPath("/login")).toBe(true);
  });

  it("lets every API path through, not just the auth ones", () => {
    // Redirecting a fetch answers it with a 200 and an HTML body, which the caller
    // parses as JSON and reports as a mystery. An expired session has to come back
    // as a real 401 so the app can say "your session ended".
    expect(isPublicPath("/api/auth/login/options")).toBe(true);
    expect(isPublicPath("/api/net-worth")).toBe(true);
  });

  it("guards the app's own pages", () => {
    expect(isPublicPath("/")).toBe(false);
    expect(isPublicPath("/accounts")).toBe(false);
    expect(isPublicPath("/transactions")).toBe(false);
  });

  it("does not treat a lookalike prefix as public", () => {
    expect(isPublicPath("/logins-are-fun")).toBe(false);
  });
});

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
  it("is public, or Fly cannot check a machine that has no session", () => {
    // The check used to point at "/", which now redirects. Fly reads the 307 as a
    // failing machine and the deploy times out on one that is serving correctly.
    expect(isPublicPath("/healthz")).toBe(true);
  });
});

describe("the health path and Cloudflare Access", () => {
  it("is exempt from the auth redirect", () => {
    expect(isPublicPath("/healthz")).toBe(true);
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

describe("the forbidden page", () => {
  it("tells a locked-out person what to try", async () => {
    // A bare "Forbidden" is indistinguishable from a genuine refusal, and it is what
    // made a stale Access session take hours to diagnose.
    vi.stubEnv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CF_ACCESS_AUD", "abc123");

    const body = await (await proxy(new NextRequest("http://localhost:3000/"))).text();

    expect(body).toContain("Clear cookies");
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
