import { describe, expect, it } from "vitest";

import { isEnforced, readConfig, verifyAccessJwt } from "@/lib/access";
import { isPublicPath } from "@/proxy";

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
