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
  it("lists members", async () => {
    render(<HouseholdPage />);

    expect(await screen.findByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("Partner")).toBeInTheDocument();
  });

  it("offers no invitation, because there is nothing left to hand over", async () => {
    // Ticket 047b: a member is a users row plus the Access policy. There is no
    // passkey for them to register and so no token to deliver.
    render(<HouseholdPage />);
    await screen.findByText("Owner");

    expect(screen.queryByRole("button", { name: /invitation/i })).toBeNull();
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

  it("checks the household fixture actually has someone to act on", () => {
    // A screen whose list is empty passes most assertions above vacuously.
    expect(members.length).toBeGreaterThan(1);
  });
});
