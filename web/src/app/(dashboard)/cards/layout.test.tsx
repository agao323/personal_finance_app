/**
 * The screen does not flash. (Ticket 070)
 *
 * Every test here is about one distinction: *nothing has arrived yet* versus *what is on
 * screen is one revision old*. Conflating them is what turned marking a single credit into
 * a full-screen rebuild, and a component test is the only place that difference shows —
 * a test that merely waits for the settled state cannot see it.
 *
 * The reload is triggered through the context rather than by clicking a particular
 * control, because the behaviour belongs to the layout: whichever panel says "something
 * changed", the wallet must stay put while it reloads.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardsLayout from "./layout";
import { useCards } from "@/components/cards/context";
import { cards, mockCards, server } from "@/test/msw";

vi.mock("next/navigation", () => ({ usePathname: () => "/cards" }));

/** Stands in for any panel that has just changed something. */
function Detail() {
  const { reload } = useCards();
  return (
    <button type="button" onClick={reload}>
      Something changed
    </button>
  );
}

function renderLayout() {
  return render(
    <CardsLayout>
      <Detail />
    </CardsLayout>,
  );
}

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("cards layout", () => {
  it("shows a skeleton only until the first response arrives", async () => {
    renderLayout();

    expect(screen.getByLabelText("Loading")).toBeInTheDocument();

    expect(await screen.findByText("Sapphire Reserve")).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading")).not.toBeInTheDocument();
  });

  it("keeps the wallet on screen while it refreshes", async () => {
    renderLayout();
    await screen.findByText("Sapphire Reserve");

    // Held open so the mid-flight state is observable at all.
    // A holder rather than a bare `let`: TypeScript narrows a local assigned only inside
    // a closure to `null`, and the release call then fails to type-check.
    const gate: { release: (() => void) | null } = { release: null };
    server.use(
      http.get("/api/cards", async () => {
        await new Promise<void>((resolve) => {
          gate.release = resolve;
        });
        return HttpResponse.json(cards);
      }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Something changed" }));

    await waitFor(() => expect(gate.release).not.toBeNull());
    expect(screen.getByText("Sapphire Reserve")).toBeInTheDocument();
    expect(screen.getByText("Refreshing")).toBeInTheDocument();
    // The assertion the ticket exists for.
    expect(screen.queryByLabelText("Loading")).not.toBeInTheDocument();

    gate.release?.();
    await waitFor(() => expect(screen.queryByText("Refreshing")).not.toBeInTheDocument());
    expect(screen.getByText("Sapphire Reserve")).toBeInTheDocument();
  });

  it("keeps the wallet when a refresh fails, and says the refresh failed", async () => {
    renderLayout();
    await screen.findByText("Sapphire Reserve");

    server.use(
      http.get("/api/cards", () => HttpResponse.json({ detail: "nope" }, { status: 500 })),
    );
    await userEvent.click(screen.getByRole("button", { name: "Something changed" }));

    // A failed refresh has not made the figures wrong. Blanking them would lose more than
    // the failure did.
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not refresh");
    expect(screen.getByText("Sapphire Reserve")).toBeInTheDocument();
  });

  it("reports a first load that never arrived as a failure, not an empty wallet", async () => {
    // An empty list and a failed load look identical, and one of them means "you have no
    // cards".
    server.use(
      http.get("/api/cards", () => HttpResponse.json({ detail: "nope" }, { status: 500 })),
    );

    renderLayout();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this");
    expect(screen.queryByRole("button", { name: "Add a card" })).not.toBeInTheDocument();
  });
});
