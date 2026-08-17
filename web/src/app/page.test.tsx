import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("connectivity page", () => {
  it("renders the readiness body once the API answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ status: "ok" })));

    render(<Home />);

    expect(await screen.findByText(/"status": "ok"/)).toBeInTheDocument();
  });

  it("requests through the proxy, not the API directly", async () => {
    const spy = vi.fn().mockResolvedValue(Response.json({ status: "ok" }));
    vi.stubGlobal("fetch", spy);

    render(<Home />);
    await screen.findByText(/"status": "ok"/);

    expect(spy.mock.calls[0][0]).toBe("/api/ready");
  });

  it("shows an alert when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(Response.json({ detail: "Upstream API unreachable" }, { status: 502 })),
    );

    render(<Home />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Upstream API unreachable/);
  });
});
