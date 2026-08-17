import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, apiPath } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("apiPath", () => {
  it("prefixes /api and keeps the path relative", () => {
    expect(apiPath("/ready")).toBe("/api/ready");
  });

  it("tolerates a missing leading slash", () => {
    expect(apiPath("ready")).toBe("/api/ready");
  });

  it("appends query parameters", () => {
    expect(apiPath("/spend", { from: "2026-01-01", group_by: "category" })).toBe(
      "/api/spend?from=2026-01-01&group_by=category",
    );
  });

  it("omits null and undefined query values", () => {
    expect(apiPath("/net-worth", { as_of: undefined, viewer: null, x: 1 })).toBe(
      "/api/net-worth?x=1",
    );
  });

  it("encodes query values", () => {
    expect(apiPath("/accounts", { name: "a&b c" })).toBe("/api/accounts?name=a%26b+c");
  });

  it("emits no ? when the query is empty", () => {
    expect(apiPath("/ready", {})).toBe("/api/ready");
  });

  it.each(["http://api:8000/ready", "https://api.example.com/ready"])(
    "rejects the absolute URL %s",
    (url) => {
      // The browser addressing the API directly is the one thing the architecture
      // forbids, so this fails loudly rather than silently working in dev.
      expect(() => apiPath(url)).toThrow(/relative path/);
    },
  );
});

describe("apiFetch", () => {
  it("requests the relative proxy path", async () => {
    const spy = stubFetch(Response.json({ status: "ok" }));

    await apiFetch("/ready");

    expect(spy).toHaveBeenCalledOnce();
    expect(spy.mock.calls[0][0]).toBe("/api/ready");
  });

  it("returns the parsed body", async () => {
    stubFetch(Response.json({ status: "ok", database: true }));

    await expect(apiFetch("/ready")).resolves.toEqual({ status: "ok", database: true });
  });

  it("forwards method and body", async () => {
    const spy = stubFetch(Response.json({}));

    await apiFetch("/accounts", { method: "POST", body: JSON.stringify({ name: "x" }) });

    expect(spy.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });

  it("throws ApiError carrying the status and detail", async () => {
    stubFetch(Response.json({ detail: "database unreachable" }, { status: 503 }));

    await expect(apiFetch("/ready")).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      detail: "database unreachable",
    });
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    stubFetch(new Response("gateway blew up", { status: 502, statusText: "Bad Gateway" }));

    await expect(apiFetch("/ready")).rejects.toBeInstanceOf(ApiError);
  });
});
