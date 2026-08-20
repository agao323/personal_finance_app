import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RedeemScreen } from "./page";
import { server } from "@/test/msw";

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams("token=abc") }));
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams.current }));

const assign = vi.fn();

beforeEach(() => {
  searchParams.current = new URLSearchParams("token=abc");
  assign.mockClear();
  vi.stubGlobal("location", {
    assign,
    href: "https://allofmymoney.com/invitation?token=abc",
    origin: "https://allofmymoney.com",
    pathname: "/invitation",
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
    http.post("/api/auth/invitation/redeem/options", () =>
      HttpResponse.json({
        options: { challenge: "AQID", user: { id: "BAUG" } },
        challenge_id: "c1",
      }),
    ),
    http.post("/api/auth/invitation/redeem/verify", () =>
      HttpResponse.json({ user_id: 2, email: "partner@example.invalid", display_name: "Partner" }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("redeeming an invitation", () => {
  it("registers a passkey and goes to the dashboard", async () => {
    render(<RedeemScreen />);

    await userEvent.click(screen.getByRole("button", { name: "Register a passkey" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("uses the invitation route, never the ordinary registration one", async () => {
    // The ordinary route registers for whoever is signed in — an owner opening this
    // link would bind the newcomer's authenticator to their own account, and every
    // ownership figure in this app is per-user.
    const called: string[] = [];
    server.use(
      http.post("/api/auth/register/options", () => {
        called.push("ordinary");
        return HttpResponse.json({ options: {}, challenge_id: "x" });
      }),
      http.post("/api/auth/invitation/redeem/options", () => {
        called.push("invitation");
        return HttpResponse.json({
          options: { challenge: "AQID", user: { id: "BAUG" } },
          challenge_id: "c1",
        });
      }),
    );

    render(<RedeemScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Register a passkey" }));

    await waitFor(() => expect(called).toEqual(["invitation"]));
  });

  it("says so when the link has no token", () => {
    searchParams.current = new URLSearchParams();

    render(<RedeemScreen />);

    expect(screen.getByRole("alert")).toHaveTextContent("missing its invitation code");
  });

  it("surfaces a spent or expired invitation", async () => {
    server.use(
      http.post("/api/auth/invitation/redeem/options", () =>
        HttpResponse.json({ detail: "That invitation is not valid" }, { status: 401 }),
      ),
    );

    render(<RedeemScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Register a passkey" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
  });

  it("says a cancelled prompt changed nothing", async () => {
    const cancelled = new Error("cancelled");
    cancelled.name = "NotAllowedError";
    vi.stubGlobal("navigator", { credentials: { create: vi.fn().mockRejectedValue(cancelled) } });

    render(<RedeemScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Register a passkey" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("nothing has changed");
  });

  it("explains itself when the browser cannot do passkeys", () => {
    vi.unstubAllGlobals();
    vi.stubGlobal("location", { href: "https://allofmymoney.com/invitation?token=abc" });

    render(<RedeemScreen />);

    expect(screen.getByRole("alert")).toHaveTextContent("no passkey support");
  });
});
