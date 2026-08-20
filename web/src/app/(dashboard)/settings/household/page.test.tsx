import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HouseholdPage from "./page";
import { members, mockMembers, server } from "@/test/msw";

beforeEach(() => {
  mockMembers();
  // `href` matters as much as `origin`: relative fetches resolve against it, and a
  // stub without one makes every request fail with "Invalid URL" before reaching MSW.
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/settings/household",
    pathname: "/settings/household",
  });
});

describe("household", () => {
  it("lists members and whether they can sign in yet", async () => {
    render(<HouseholdPage />);

    expect(await screen.findByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("2 passkeys")).toBeInTheDocument();
    expect(screen.getByText("No passkey yet — they cannot sign in")).toBeInTheDocument();
  });

  it("only offers an invitation to someone with no passkey", async () => {
    // Someone who already has one adds devices from their own account.
    render(<HouseholdPage />);
    await screen.findByText("Owner");

    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).queryByRole("button", { name: "Create invitation" })).toBeNull();
    expect(within(rows[1]).getByRole("button", { name: "Create invitation" })).toBeInTheDocument();
  });

  it("shows the invitation link once, and says so", async () => {
    // Only the hash is stored, so it genuinely cannot be retrieved later.
    render(<HouseholdPage />);
    await screen.findByText("Owner");

    await userEvent.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(await screen.findByText(/copy it now/)).toBeInTheDocument();
    expect(
      screen.getByText("https://allofmymoney.com/invitation?token=invitation-token"),
    ).toBeInTheDocument();
  });

  it("adds a member", async () => {
    render(<HouseholdPage />);
    await screen.findByText("Owner");

    await userEvent.type(screen.getByLabelText("Email"), "third@example.invalid");
    await userEvent.type(screen.getByLabelText("Display name"), "Third");
    await userEvent.click(screen.getByRole("button", { name: "Add member" }));

    expect(await screen.findByText("Third")).toBeInTheDocument();
  });

  it("surfaces a duplicate rather than silently doing nothing", async () => {
    server.use(
      http.post("/api/members", () =>
        HttpResponse.json({ detail: "That email is already a member" }, { status: 409 }),
      ),
    );

    render(<HouseholdPage />);
    await screen.findByText("Owner");
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.invalid");
    await userEvent.type(screen.getByLabelText("Display name"), "Dup");
    await userEvent.click(screen.getByRole("button", { name: "Add member" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already a member");
  });

  it("deactivates and reactivates", async () => {
    render(<HouseholdPage />);
    await screen.findByText("Partner");

    const rows = screen.getAllByRole("listitem");
    await userEvent.click(within(rows[1]).getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(screen.getByText("inactive")).toBeInTheDocument());
  });

  it("states the two steps it cannot perform", async () => {
    // Missing the Access policy entry looks, from their side, exactly like being
    // refused — so this screen has to say it rather than let it be discovered.
    render(<HouseholdPage />);

    expect(await screen.findByText(/Cloudflare Access policy/)).toBeInTheDocument();
    expect(screen.getByText(/never reach this app at all/)).toBeInTheDocument();
  });

  it("says nothing about members it could not load", async () => {
    server.use(
      http.get("/api/members", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    render(<HouseholdPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("That did not work");
  });

  it("checks the household fixture actually exercises both states", () => {
    expect(members.some((m) => m.passkey_count === 0)).toBe(true);
    expect(members.some((m) => m.passkey_count > 0)).toBe(true);
  });
});
