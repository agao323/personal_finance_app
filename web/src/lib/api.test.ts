import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, apiPath, fillPath } from "@/lib/api";

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

  it("defaults to GET and asks for JSON", async () => {
    const spy = stubFetch(Response.json({ status: "ok" }));

    await apiFetch("/health");

    expect(spy.mock.calls[0][1]).toMatchObject({ method: "GET" });
    expect(spy.mock.calls[0][1].headers).toMatchObject({ accept: "application/json" });
  });

  it("sends no content-type when there is no body", async () => {
    const spy = stubFetch(Response.json({ status: "ok" }));

    await apiFetch("/health");

    expect(spy.mock.calls[0][1].headers).not.toHaveProperty("content-type");
  });

  it("forwards an abort signal", async () => {
    const spy = stubFetch(Response.json({ status: "ok" }));
    const controller = new AbortController();

    await apiFetch("/ready", { signal: controller.signal });

    expect(spy.mock.calls[0][1].signal).toBe(controller.signal);
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

describe("contract enforcement", () => {
  it("rejects routes the API does not declare", () => {
    // Compile-time guarantee, asserted here so the reason is discoverable. /accounts
    // used to fail this check and now passes — 012 put it in the contract. That is the
    // mechanism working: a route becomes callable exactly when a Pydantic model
    // declares it, never before.
    //
    // @ts-expect-error "/not-a-route" is not a path in the generated contract
    const rejected = () => apiFetch("/not-a-route");

    expect(typeof rejected).toBe("function");
  });

  it("types a write body from the route string", async () => {
    const spy = stubFetch(Response.json({ id: 1 }, { status: 201 }));

    await apiFetch("/accounts", {
      method: "post",
      body: { name: "Checking", kind: "liquid_asset", subtype: "checking" },
    });

    expect(spy.mock.calls[0][0]).toBe("/api/accounts");
    expect(spy.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });

  it("rejects a write body that does not match the contract", () => {
    const rejected = () =>
      apiFetch("/accounts", {
        method: "post",
        // @ts-expect-error `kind` is a literal union; "crypto" is not a member
        body: { name: "X", kind: "crypto", subtype: "checking" },
      });

    expect(typeof rejected).toBe("function");
  });
});

describe("fillPath", () => {
  it("substitutes a path parameter", () => {
    expect(fillPath("/accounts/{account_id}", { account_id: 7 })).toBe("/accounts/7");
  });

  it("substitutes every placeholder in a route", () => {
    expect(fillPath("/a/{x}/b/{y}", { x: 1, y: "two" })).toBe("/a/1/b/two");
  });

  it("leaves a route with no placeholders alone", () => {
    expect(fillPath("/accounts")).toBe("/accounts");
  });

  it("throws rather than leaving a placeholder in the URL", () => {
    // An unsubstituted `/accounts/%7Baccount_id%7D` comes back 404 or 422, and the
    // bug report that follows is about the wrong thing entirely.
    expect(() => fillPath("/accounts/{account_id}", {})).toThrow(/Missing path parameter/);
  });

  it("escapes a value that would otherwise change the path", () => {
    expect(fillPath("/accounts/{account_id}", { account_id: "../rules" })).toBe(
      "/accounts/..%2Frules",
    );
  });
});
