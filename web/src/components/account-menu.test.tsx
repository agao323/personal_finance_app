import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountMenu } from "@/components/account-menu";
import { mockNoSession, mockSession } from "@/test/msw";

beforeEach(() => {
  // `href` as well as `origin`: relative fetches resolve against `href`, and a stub
  // without it breaks every request in the component under test. That has cost time
  // twice in this codebase now.
  vi.stubGlobal("location", {
    pathname: "/",
    href: "http://localhost:3000/",
    origin: "http://localhost:3000",
  });
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

  it("shows nothing at all when the app refuses the identity", async () => {
    // Whoever this is passed Access and is not an active member here. There is no
    // sign-in to offer them — Access already signed them in — so the control is simply
    // absent rather than inviting an action that cannot help.
    mockNoSession();

    const { container } = render(<AccountMenu />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("offers the email and a single sign-out", async () => {
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));

    expect(screen.getByText("owner@example.invalid")).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(1);
  });

  it("signs out through Cloudflare, because that is the only session", async () => {
    // A link the browser follows, not a fetch: `/cdn-cgi/access/logout` is served by
    // the edge and needs a real navigation for its redirect to land. There is no
    // application session left to end first.
    mockSession();

    render(<AccountMenu />);
    await userEvent.click(await screen.findByRole("button", { name: /Owner/ }));

    expect(screen.getByRole("menuitem", { name: /Sign out/ })).toHaveAttribute(
      "href",
      "/cdn-cgi/access/logout",
    );
  });
});
