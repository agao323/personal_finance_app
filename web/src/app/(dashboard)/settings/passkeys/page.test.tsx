import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PasskeysPage from "./page";
import { credentials, mockCredentials, server } from "@/test/msw";

beforeEach(() => {
  mockCredentials();
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
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("passkeys", () => {
  it("lists each registered device", async () => {
    render(<PasskeysPage />);

    expect(await screen.findByText(/Registered Mar 1, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Registered Jul 14, 2026/)).toBeInTheDocument();
  });

  it("marks the device you are signed in with", async () => {
    // Removing the one you are holding is a different decision from removing one you
    // lost, and a list that cannot tell them apart invites the wrong click.
    render(<PasskeysPage />);

    await screen.findByText(/Registered Mar 1, 2026/);
    expect(screen.getByText("this device")).toBeInTheDocument();
  });

  it("says when a passkey has never been used", async () => {
    render(<PasskeysPage />);

    expect(await screen.findByText("Never used to sign in")).toBeInTheDocument();
  });

  it("removes one", async () => {
    render(<PasskeysPage />);
    await screen.findByText(/Registered Mar 1, 2026/);

    const rows = screen.getAllByRole("listitem");
    await userEvent.click(within(rows[0]).getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(screen.queryByText(/Registered Mar 1, 2026/)).not.toBeInTheDocument(),
    );
  });

  it("will not let you remove your only passkey", async () => {
    // The API refuses with a 409. This disables the control before you try, because
    // there is no undo behind it — the bootstrap window is shut for good.
    mockCredentials([credentials[1]]);

    render(<PasskeysPage />);
    await screen.findByText(/Registered Jul 14, 2026/);

    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
    expect(screen.getByText(/cannot be recovered from inside the app/)).toBeInTheDocument();
  });

  it("registers this device", async () => {
    const sent: string[] = [];
    server.use(
      http.post("/api/auth/register/options", () => {
        sent.push("options");
        return HttpResponse.json({
          options: { challenge: "AQID", user: { id: "BAUG" } },
          challenge_id: "c1",
        });
      }),
      http.post("/api/auth/register/verify", () => {
        sent.push("verify");
        return HttpResponse.json({ user_id: 1, email: "o@e.invalid", display_name: "Owner" });
      }),
    );

    render(<PasskeysPage />);
    await screen.findByText(/Registered Mar 1, 2026/);
    await userEvent.click(screen.getByRole("button", { name: "Register this device" }));

    await waitFor(() => expect(sent).toEqual(["options", "verify"]));
  });

  it("says a cancelled prompt changed nothing", async () => {
    const cancelled = new Error("cancelled");
    cancelled.name = "NotAllowedError";
    vi.stubGlobal("navigator", { credentials: { create: vi.fn().mockRejectedValue(cancelled) } });
    server.use(
      http.post("/api/auth/register/options", () =>
        HttpResponse.json({
          options: { challenge: "AQID", user: { id: "BAUG" } },
          challenge_id: "c",
        }),
      ),
    );

    render(<PasskeysPage />);
    await screen.findByText(/Registered Mar 1, 2026/);
    await userEvent.click(screen.getByRole("button", { name: "Register this device" }));

    expect(await screen.findByText(/nothing has changed/)).toBeInTheDocument();
  });

  it("surfaces the API's own reason for refusing a removal", async () => {
    // Better than inventing a message here that could drift from the actual rule.
    server.use(
      http.delete("/api/auth/credentials/:id", () =>
        HttpResponse.json({ detail: "This is your only passkey." }, { status: 409 }),
      ),
    );

    render(<PasskeysPage />);
    await screen.findByText(/Registered Mar 1, 2026/);
    await userEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);

    expect(await screen.findByRole("alert")).toHaveTextContent("only passkey");
  });
});
