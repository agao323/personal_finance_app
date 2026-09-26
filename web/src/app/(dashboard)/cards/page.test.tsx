import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardsPage from "./page";
import { mockCards, server, upcoming } from "@/test/msw";

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("cards page", () => {
  it("leads with what is available, then the cards", async () => {
    render(<CardsPage />);

    expect(await screen.findByText("Available to use")).toBeInTheDocument();
    expect(await screen.findByText("Sapphire Reserve")).toBeInTheDocument();
  });

  it("refetches the available panel when a credit is marked from a card row", async () => {
    // Ticket 061, the bug: the panel used to fetch on a counter only its own button
    // bumped, so marking from a card row left the total and the list stale until a
    // reload. One refresh signal for the screen.
    const upcomingRequests: string[] = [];
    server.use(
      http.get("/api/perks/upcoming", ({ request }) => {
        upcomingRequests.push(request.url);
        return HttpResponse.json(upcoming);
      }),
    );

    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");
    await waitFor(() => expect(upcomingRequests).toHaveLength(1));

    // The card row's own mark button, not the panel's.
    const rows = await screen.findAllByRole("listitem");
    const dining = rows.find((row) => within(row).queryByText("Dining credit"));
    await userEvent.click(within(dining!).getByRole("button", { name: /Used|Mark used/ }));

    await waitFor(() => expect(upcomingRequests.length).toBeGreaterThan(1));
  });

  it("points at accounts when there are no cards, rather than dead-ending", async () => {
    server.use(http.get("/api/cards", () => HttpResponse.json([])));

    render(<CardsPage />);

    expect(await screen.findByText("No credit cards yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a card" })).toHaveAttribute(
      "href",
      "/accounts/new",
    );
  });

  it("reports a failed load rather than an empty page", async () => {
    server.use(http.get("/api/cards", () => HttpResponse.json({ detail: "no" }, { status: 500 })));

    render(<CardsPage />);

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("Could not load this"))).toBe(true);
  });
});
