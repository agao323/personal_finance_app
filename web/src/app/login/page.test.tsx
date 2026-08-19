import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginScreen, safeNext } from "./page";
import { server } from "@/test/msw";

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams.current }));

const assign = vi.fn();

beforeEach(() => {
  searchParams.current = new URLSearchParams();
  assign.mockClear();
  // jsdom has no WebAuthn. Standing one up is what makes the ceremony testable at
  // all — the real one needs an authenticator and lands in ticket 038's E2E run.
  vi.stubGlobal("PublicKeyCredential", class {});
  vi.stubGlobal("navigator", {
    credentials: {
      create: vi.fn().mockResolvedValue(fakeCredential()),
      get: vi.fn().mockResolvedValue(fakeCredential()),
    },
  });
  // `href` matters: relative fetches resolve against it, and a stub without one
  // makes every request fail with "Invalid URL" rather than reaching MSW.
  vi.stubGlobal("location", {
    assign,
    pathname: "/",
    href: "http://localhost:3000/",
    origin: "http://localhost:3000",
  });

  server.use(
    http.post("/api/auth/login/options", () =>
      HttpResponse.json({ options: { challenge: "AQID" }, challenge_id: "c1" }),
    ),
    http.post("/api/auth/register/options", () =>
      HttpResponse.json({
        options: { challenge: "AQID", user: { id: "BAUG" } },
        challenge_id: "c2",
      }),
    ),
    http.post("/api/auth/login/verify", () =>
      HttpResponse.json({ user_id: 1, email: "owner@example.invalid", display_name: "Owner" }),
    ),
    http.post("/api/auth/register/verify", () =>
      HttpResponse.json({ user_id: 1, email: "owner@example.invalid", display_name: "Owner" }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeCredential() {
  return {
    id: "abc",
    rawId: Uint8Array.from([1]).buffer,
    type: "public-key",
    response: {
      clientDataJSON: Uint8Array.from([2]).buffer,
      attestationObject: Uint8Array.from([3]).buffer,
      authenticatorData: Uint8Array.from([3]).buffer,
      signature: Uint8Array.from([4]).buffer,
      userHandle: null,
    },
    getClientExtensionResults: () => ({}),
  };
}

describe("safeNext", () => {
  it("keeps an in-app path", () => {
    expect(safeNext("/transactions?uncategorised=true")).toBe("/transactions?uncategorised=true");
  });

  it("refuses an absolute URL", () => {
    expect(safeNext("https://evil.example")).toBe("/");
  });

  it("refuses a protocol-relative URL", () => {
    // The case a naive startsWith("/") check misses.
    expect(safeNext("//evil.example")).toBe("/");
  });
});

describe("login", () => {
  it("offers no password field, because there is no password", () => {
    render(<LoginScreen />);

    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it("signs in and navigates where the visitor was going", async () => {
    searchParams.current = new URLSearchParams("next=%2Ftransactions");

    render(<LoginScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/transactions"));
  });

  it("refuses an off-site next parameter", async () => {
    // An open redirect on a sign-in page is how a phishing link borrows your domain.
    searchParams.current = new URLSearchParams("next=https%3A%2F%2Fevil.example");

    render(<LoginScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("registers a passkey", async () => {
    render(<LoginScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Register a passkey" }));

    await waitFor(() => expect(assign).toHaveBeenCalled());
  });

  it("says a cancelled prompt changed nothing", async () => {
    // A cancelled Touch ID throws. It is not a failure worth alarm, but silence
    // would leave the reader wondering whether it worked.
    const error = new Error("cancelled");
    error.name = "NotAllowedError";
    vi.stubGlobal("navigator", { credentials: { get: vi.fn().mockRejectedValue(error) } });

    render(<LoginScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("nothing has changed");
  });

  it("surfaces a refused passkey", async () => {
    server.use(
      http.post("/api/auth/login/verify", () =>
        HttpResponse.json({ detail: "Could not verify that passkey" }, { status: 401 }),
      ),
    );

    render(<LoginScreen />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not verify that passkey");
  });

  it("explains itself when the browser cannot do passkeys", () => {
    vi.unstubAllGlobals();

    render(<LoginScreen />);

    expect(screen.getByRole("alert")).toHaveTextContent("no passkey support");
    expect(
      screen.queryByRole("button", { name: "Sign in with a passkey" }),
    ).not.toBeInTheDocument();
  });

  it("says so when arriving from an expired session", () => {
    searchParams.current = new URLSearchParams("expired=1");

    render(<LoginScreen />);

    expect(screen.getByText(/Your session ended/)).toBeInTheDocument();
  });
});
