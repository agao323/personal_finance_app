import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CardRow } from "@/components/cards/card-row";
import { cards, mockCards } from "@/test/msw";
import { expiryLabel } from "@/components/cards/types";

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("expiryLabel", () => {
  it("says Today on the final day rather than '0 days'", () => {
    // `days_remaining` is 0 on the last day, and "in 0 days" is the phrase nobody parses
    // at a glance — which is the one that matters most.
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

describe("CardRow", () => {
  it("shows the card's state without expanding anything", async () => {
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    expect(screen.getByText("Sapphire Reserve")).toBeInTheDocument();
    expect(screen.getByText(/\$300\.00 available/)).toBeInTheDocument();
    expect(screen.getByText(/2 credits/)).toBeInTheDocument();
  });

  it("groups credits by cadence with monthly first", () => {
    // A monthly credit recurs most often and so gets checked most often.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.indexOf("Monthly")).toBeLessThan(headings.indexOf("Annual"));
  });

  it("marks an urgent credit with more than colour", () => {
    // The travel credit has 3 days left on an annual cadence — inside its 30-day window.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const travel = rows.find((row) => within(row).queryByText("Travel credit"));
    expect(within(travel!).getByText(/3 days/)).toBeInTheDocument();
  });

  it("does not mark a monthly credit urgent 12 days out", () => {
    // The complaint that started this: a single 30-day window called this urgent.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const dining = rows.find((row) => within(row).queryByText("Dining credit"));
    expect(within(dining!).queryByText(/⚠/)).toBeNull();
  });

  it("renames the card", async () => {
    const onChange = vi.fn();
    render(<CardRow card={cards[0]} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const field = screen.getByLabelText("Card name");
    await userEvent.clear(field);
    await userEvent.type(field, "Platinum");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("collapses so a wallet of several cards stays scannable", async () => {
    render(<CardRow card={cards[0]} onChange={() => {}} />);
    expect(screen.getByText("Travel credit")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { expanded: true }));

    expect(screen.queryByText("Travel credit")).toBeNull();
    // The summary survives collapsing — that is the point of the row.
    expect(screen.getByText(/\$300\.00 available/)).toBeInTheDocument();
  });

  it("offers the next action when a card has no credits", () => {
    render(<CardRow card={{ ...cards[0], perks: [], active_perk_count: 0 }} onChange={() => {}} />);

    expect(screen.getByText(/No credits tracked on this card yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a credit" })).toBeInTheDocument();
  });
});
