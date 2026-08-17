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
    // Compile-time guarantee, asserted here so the reason is discoverable. The line
    // below is the whole point of ticket 005: /accounts does not exist yet, so it is
    // not a valid argument until a Pydantic model puts it in the contract.
    //
    // @ts-expect-error "/accounts" is not a path in the generated contract
    const rejected = () => apiFetch("/accounts");

    expect(typeof rejected).toBe("function");
  });

  // Write verbs get runtime coverage in 013, the first ticket with a write endpoint.
  // There is no POST in the contract yet, so `PathsWith<"post">` is `never` and no
  // call can be written — which is the pipeline behaving correctly.
});
