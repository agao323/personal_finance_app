import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountMenu } from "@/components/account-menu";
import { mockCredentials, mockNoSession, mockSession } from "@/test/msw";

const assign = vi.fn();

beforeEach(() => {
  assign.mockClear();
  vi.stubGlobal("location", {
    assign,
    pathname: "/",
    href: "http://localhost:3000/",
    origin: "http://localhost:3000",
  });
  mockCredentials();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AccountMenu", () => {
  it("names who is signed in", async () => {
    mockSession();

    render(<AccountMenu />);

    expect(await screen.findByRole("button", { name: /Owner/ })).toBeInTheDocument();
  });

  it("shows nothing at all when there is no session", async () => {
    // The expiry bar says what happened. This control simply has nothing to show.
    mockNoSession();

    const { container } = render(<AccountMenu />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("offers the email and a link to passkeys", async () => {
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));

    expect(screen.getByText("owner@example.invalid")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Passkeys" })).toHaveAttribute(
      "href",
      "/settings/passkeys",
    );
  });

  it("signs out of the app and lands on the sign-in page", async () => {
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  });

  it("offers a separate action that also ends the Access session", async () => {
    // Collapsing these would be wrong in both directions: app-only leaves a "signed
    // out" state Access still waves through, and always-both makes the ordinary case
    // cost a full Access round trip.
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: /Sign out of Access too/ }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/cdn-cgi/access/logout"));
  });

  it("still navigates when logout itself fails", async () => {
    // Refusing to leave because the sign-out call errored strands the person trying
    // to leave. The cookie is the server's to clear and may already be gone.
    mockSession();
    const { server } = await import("@/test/msw");
    const { http, HttpResponse } = await import("msw");
    server.use(
      http.post("/api/auth/logout", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  });

  it("closes when you click away", async () => {
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { hidden: true, name: "" }));

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
