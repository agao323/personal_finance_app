import type { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const INTERNAL = "http://api:8000";

function request(url: string, init?: RequestInit): NextRequest {
  return new Request(url, init) as unknown as NextRequest;
}

function context(...segments: string[]) {
  return { params: Promise.resolve({ path: segments }) } as Parameters<typeof GET>[1];
}

beforeEach(() => {
  vi.stubEnv("INTERNAL_API_URL", INTERNAL);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("proxy route", () => {
  it("forwards the path to the internal API", async () => {
    const spy = vi.fn().mockResolvedValue(Response.json({ status: "ok" }));
    vi.stubGlobal("fetch", spy);

    await GET(request("http://localhost:3000/api/ready"), context("ready"));

    expect(spy.mock.calls[0][0]).toBe(`${INTERNAL}/ready`);
  });

  it("preserves nested paths and the query string", async () => {
    const spy = vi.fn().mockResolvedValue(Response.json({}));
    vi.stubGlobal("fetch", spy);

    await GET(
      request("http://localhost:3000/api/accounts/7/history?from=2026-01-01"),
      context("accounts", "7", "history"),
    );

    expect(spy.mock.calls[0][0]).toBe(`${INTERNAL}/accounts/7/history?from=2026-01-01`);
  });

  it("passes the upstream status through", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ detail: "nope" }, { status: 404 })),
    );

    const response = await GET(request("http://localhost:3000/api/missing"), context("missing"));

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({ detail: "nope" });
  });

  it("forwards the method and body for writes", async () => {
    const spy = vi.fn().mockResolvedValue(Response.json({}, { status: 201 }));
    vi.stubGlobal("fetch", spy);

    const response = await POST(
      request("http://localhost:3000/api/accounts", {
        method: "POST",
        body: JSON.stringify({ name: "Checking" }),
        headers: { "content-type": "application/json" },
      }),
      context("accounts"),
    );

    expect(spy.mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(response.status).toBe(201);
  });

  it("strips hop-by-hop and host headers", async () => {
    const spy = vi.fn().mockResolvedValue(Response.json({}));
    vi.stubGlobal("fetch", spy);

    await GET(
      request("http://localhost:3000/api/ready", {
        headers: { connection: "keep-alive", host: "localhost:3000", "x-request-id": "abc" },
      }),
      context("ready"),
    );

    const sent = spy.mock.calls[0][1].headers as Headers;
    expect(sent.get("connection")).toBeNull();
    expect(sent.get("host")).toBeNull();
    expect(sent.get("x-request-id")).toBe("abc");
  });

  it("returns 502 when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    const response = await GET(request("http://localhost:3000/api/ready"), context("ready"));

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({ detail: "Upstream API unreachable" });
  });

  it("returns 500 when INTERNAL_API_URL is unset", async () => {
    vi.stubEnv("INTERNAL_API_URL", "");
    vi.stubGlobal("fetch", vi.fn());

    const response = await GET(request("http://localhost:3000/api/ready"), context("ready"));

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toMatchObject({
      detail: expect.stringContaining("INTERNAL_API_URL"),
    });
  });
});
