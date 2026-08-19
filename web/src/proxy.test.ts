import { describe, expect, it } from "vitest";

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
