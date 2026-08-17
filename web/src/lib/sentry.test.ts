import { afterEach, describe, expect, it, vi } from "vitest";

import { __testing, initSentry } from "@/lib/sentry";

const { redact } = __testing;

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("initSentry", () => {
  it("is disabled when no DSN is configured", () => {
    expect(initSentry(undefined)).toBe(false);
    expect(initSentry("")).toBe(false);
  });

  it("reads the DSN from a server-only variable", () => {
    // A NEXT_PUBLIC_ counterpart would ship the DSN to the browser and start
    // sending client breadcrumbs, which on this app means balances.
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://public@example.com/1");
    vi.stubEnv("SENTRY_DSN", "");

    expect(initSentry()).toBe(false);
  });
});

describe("redaction", () => {
  it("replaces monetary fields", () => {
    expect(redact({ balance: 100, account_id: 1 })).toEqual({
      balance: "[redacted]",
      account_id: 1,
    });
  });

  it("walks nested objects", () => {
    expect(redact({ account: { name: "Checking", net_worth: 5 } })).toEqual({
      account: { name: "Checking", net_worth: "[redacted]" },
    });
  });

  it("walks arrays", () => {
    expect(redact({ rows: [{ amount: 1 }, { amount: 2 }] })).toEqual({
      rows: [{ amount: "[redacted]" }, { amount: "[redacted]" }],
    });
  });

  it("matches compound and plural names", () => {
    expect(redact({ opening_balance: 1, totals: 2, purchase_price: 3 })).toEqual({
      opening_balance: "[redacted]",
      totals: "[redacted]",
      purchase_price: "[redacted]",
    });
  });

  it("leaves non-monetary fields alone", () => {
    expect(redact({ method: "GET", path: "/api/ready", status: 200 })).toEqual({
      method: "GET",
      path: "/api/ready",
      status: 200,
    });
  });

  it("leaves primitives untouched", () => {
    expect(redact("plain")).toBe("plain");
    expect(redact(7)).toBe(7);
    expect(redact(null)).toBeNull();
  });
});
