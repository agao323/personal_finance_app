import { describe, expect, it } from "vitest";

import nextConfig, { CONTENT_SECURITY_POLICY, CSP_DIRECTIVES } from "../next.config";

async function headersForEveryRoute() {
  const rules = await nextConfig.headers!();
  const everything = rules.find((rule) => rule.source === "/:path*");
  expect(everything, "a header rule that matches every route").toBeDefined();
  return new Map(everything!.headers.map((header) => [header.key, header.value]));
}

describe("the content security policy", () => {
  it("is sent on every route", async () => {
    const headers = await headersForEveryRoute();

    expect(headers.get("Content-Security-Policy")).toBe(CONTENT_SECURITY_POLICY);
  });

  it("lets images and connections reach this origin only", () => {
    expect(CSP_DIRECTIVES["img-src"]).toBe("'self' data: blob:");
    expect(CSP_DIRECTIVES["connect-src"]).toBe("'self'");
    for (const directive of ["img-src", "connect-src"]) {
      const sources = CSP_DIRECTIVES[directive].split(/\s+/);
      expect(
        sources.some((source) => source.includes("*")),
        directive,
      ).toBe(false);
      expect(
        sources.some((source) => /^https?:/.test(source)),
        directive,
      ).toBe(false);
    }
  });

  it("forbids framing and plugins, and pins the base and form targets", () => {
    expect(CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'");
    expect(CONTENT_SECURITY_POLICY).toContain("object-src 'none'");
    expect(CONTENT_SECURITY_POLICY).toContain("base-uri 'self'");
    expect(CONTENT_SECURITY_POLICY).toContain("form-action 'self'");
  });
});
