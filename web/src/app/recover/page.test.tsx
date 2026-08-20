import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecoverPage from "./page";
import { server } from "@/test/msw";

const assign = vi.fn();

beforeEach(() => {
  assign.mockClear();
  vi.stubGlobal("location", {
    assign,
    href: "https://allofmymoney.com/recover",
    origin: "https://allofmymoney.com",
    pathname: "/recover",
  });
  vi.stubGlobal("PublicKeyCredential", class {});
  vi.stubGlobal("navigator", {
    credentials: {
      create: vi.fn().mockResolvedValue({
        id: "abc",
        rawId: Uint8Array.from([1]).buffer,
        type: "public-key",
        response: {
          clientDataJSON: Uint8Array.from([2]).buffer,
          attestationObject: Uint8Array.from([3]).buffer,
        },
        getClientExtensionResults: () => ({}),
      }),
    },
  });
  server.use(
    http.post("/api/auth/recover/options", () =>
      HttpResponse.json({
        options: { challenge: "AQID", user: { id: "BAUG" } },
        challenge_id: "c1",
      }),
    ),
    http.post("/api/auth/recover/verify", () =>
      HttpResponse.json({ user_id: 1, email: "owner@example.invalid", display_name: "Owner" }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("recovery", () => {
  it("registers a replacement passkey and signs you in", async () => {
    render(<RecoverPage />);

    await userEvent.click(
      screen.getByRole("button", { name: "Register a passkey on this device" }),
    );

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("needs no session, which is the entire point", async () => {
    // The person using this cannot produce one — they lost the passkey that makes it.
    const seen: string[] = [];
    server.use(
      http.post("/api/auth/recover/options", ({ request }) => {
        seen.push(request.headers.get("cookie") ?? "");
        return HttpResponse.json({
          options: { challenge: "AQID", user: { id: "BAUG" } },
          challenge_id: "c1",
        });
      }),
    );

    render(<RecoverPage />);
    await userEvent.click(
      screen.getByRole("button", { name: "Register a passkey on this device" }),
    );

    await waitFor(() => expect(seen).toHaveLength(1));
  });

  it("says so when the identity is not allowed to recover", async () => {
    server.use(
      http.post("/api/auth/recover/options", () =>
        HttpResponse.json(
          { detail: "Account recovery is not available for this identity" },
          { status: 401 },
        ),
      ),
    );

    render(<RecoverPage />);
    await userEvent.click(
      screen.getByRole("button", { name: "Register a passkey on this device" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("not available");
  });

  it("says a cancelled prompt changed nothing", async () => {
    const cancelled = new Error("cancelled");
    cancelled.name = "NotAllowedError";
    vi.stubGlobal("navigator", { credentials: { create: vi.fn().mockRejectedValue(cancelled) } });

    render(<RecoverPage />);
    await userEvent.click(
      screen.getByRole("button", { name: "Register a passkey on this device" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("nothing has changed");
  });

  it("promises not to remove the old passkeys", async () => {
    // A phone that turns up in a coat pocket still works, and deciding what to remove
    // is better done signed in than while panicking.
    render(<RecoverPage />);

    expect(screen.getByText(/old passkeys are left alone/)).toBeInTheDocument();
  });

  it("explains itself when the browser cannot do passkeys", () => {
    vi.unstubAllGlobals();
    vi.stubGlobal("location", { href: "https://allofmymoney.com/recover" });

    render(<RecoverPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("no passkey support");
  });
});
