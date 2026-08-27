import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardsPage, { expiryLabel } from "./page";
import { mockCards, server } from "@/test/msw";

beforeEach(() => {
  mockCards();
  // `href` as well as `origin`: relative fetches resolve against it, and a stub
  // without one makes every request fail before it reaches MSW. Third time in this
  // codebase, hence the note.
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("expiryLabel", () => {
  it("says Today on the final day rather than '0 days'", () => {
    // `days_remaining` is 0 on the last day, and "expires in 0 days" is the sentence
    // nobody parses at a glance — which is the one that matters most.
    expect(expiryLabel(0)).toBe("Today");
    expect(expiryLabel(-1)).toBe("Today");
  });

  it("reads naturally across the near range", () => {
    expect(expiryLabel(1)).toBe("Tomorrow");
    expect(expiryLabel(3)).toBe("3 days");
    expect(expiryLabel(10)).toBe("Next week");
    expect(expiryLabel(40)).toBe("40 days");
  });
});

describe("cards page", () => {
  it("leads with what is expiring, not with the card list", async () => {
    render(<CardsPage />);

    const heading = await screen.findByText(/expiring in the next 45 days/);
    expect(heading).toHaveTextContent("$300.00");
  });

  it("lists a card with its perks and unused total", async () => {
    render(<CardsPage />);

    expect(await screen.findByText("Sapphire Reserve")).toBeInTheDocument();
    expect(screen.getByText(/\$300\.00 unused this period/)).toBeInTheDocument();
    expect(screen.getAllByText("Travel credit").length).toBeGreaterThan(0);
  });

  it("shows an already-used perk as used", async () => {
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    const rows = screen.getAllByRole("listitem");
    const dining = rows.find((row) => within(row).queryByText("Dining credit"));
    expect(dining).toBeDefined();
    expect(within(dining!).getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("marks a perk used and reflects it immediately", async () => {
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    const [markButton] = screen.getAllByRole("button", { name: "Mark used" });
    await userEvent.click(markButton);

    // Asserting the empty-state message rather than the absence of the banner: the
    // two strings overlap ("Nothing expiring in the next 45 days" contains the
    // banner's wording), so a `not.toBeInTheDocument` on the shorter one can never
    // pass. It failed for exactly that reason first time round.
    expect(await screen.findByText(/Nothing expiring in the next 45 days/)).toBeInTheDocument();
  });

  it("reverts and says so when marking fails", async () => {
    // Optimistic updates are only acceptable if a failure is visible. A row that
    // silently stays green after a failed write is worse than no optimism at all.
    server.use(
      http.post("/api/perks/:id/redemptions", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    const [markButton] = screen.getAllByRole("button", { name: "Mark used" });
    await userEvent.click(markButton);

    expect(await screen.findByRole("alert")).toHaveTextContent("Did not save");
    expect(screen.getAllByRole("button", { name: "Mark used" }).length).toBeGreaterThan(0);
  });

  it("refuses a perk with no value", async () => {
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    await userEvent.click(screen.getByRole("button", { name: "Add a perk" }));
    await userEvent.type(screen.getByLabelText("Name"), "Lounge access");
    await userEvent.click(screen.getByRole("button", { name: "Add perk" }));

    expect(await screen.findByText(/what the perk is worth/)).toBeInTheDocument();
  });

  it("refuses a perk with no anchor date", async () => {
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    await userEvent.click(screen.getByRole("button", { name: "Add a perk" }));
    await userEvent.type(screen.getByLabelText("Name"), "Lounge access");
    await userEvent.type(screen.getByLabelText("Value"), "200");
    await userEvent.click(screen.getByRole("button", { name: "Add perk" }));

    expect(await screen.findByText(/first period began/)).toBeInTheDocument();
  });

  it("explains what the anchor date means, because the label alone does not", async () => {
    // "First period began" is guessable only with the sentence underneath it. This is
    // the field most likely to be filled in wrong, and a wrong anchor silently shifts
    // every period for that perk.
    render(<CardsPage />);
    await screen.findByText("Sapphire Reserve");

    await userEvent.click(screen.getByRole("button", { name: "Add a perk" }));

    expect(screen.getByText(/cardmember year/)).toBeInTheDocument();
  });

  it("says so when there is nothing expiring", async () => {
    server.use(
      http.get("/api/perks/upcoming", () =>
        HttpResponse.json({ within_days: 45, as_of: "2026-06-18", total_cents: 0, perks: [] }),
      ),
    );
    render(<CardsPage />);

    expect(await screen.findByText(/Nothing expiring in the next 45 days/)).toBeInTheDocument();
  });

  it("reports a failed load rather than rendering an empty page", async () => {
    server.use(http.get("/api/cards", () => HttpResponse.json({ detail: "no" }, { status: 500 })));

    render(<CardsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this");
  });
});
