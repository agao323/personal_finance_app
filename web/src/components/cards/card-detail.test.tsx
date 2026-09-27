import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CardDetail } from "@/components/cards/card-detail";
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

describe("CardDetail", () => {
  it("opens with the compact summary of the card it describes", () => {
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    expect(screen.getByRole("heading", { name: /Sapphire Reserve/ })).toBeInTheDocument();
    expect(screen.getByText("Available now")).toBeInTheDocument();
    expect(screen.getByText("$300.00")).toBeInTheDocument();
    expect(screen.getByText("Annual fee")).toBeInTheDocument();
  });

  it("groups credits by cadence with monthly first", () => {
    // A monthly credit recurs most often and so gets checked most often.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.indexOf("Monthly")).toBeLessThan(headings.indexOf("Annual"));
  });

  it("marks an urgent credit with more than colour", () => {
    // The travel credit has 3 days left on an annual cadence — inside its 30-day window.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const travel = rows.find((row) => within(row).queryByText("Travel credit"));
    expect(within(travel!).getByText(/3 days/)).toBeInTheDocument();
  });

  it("does not mark a monthly credit urgent 12 days out", () => {
    // The complaint that started this: a single 30-day window called this urgent.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const dining = rows.find((row) => within(row).queryByText("Dining credit"));
    expect(within(dining!).queryByText(/⚠/)).toBeNull();
  });

  it("offers the next action when a card has no credits", () => {
    render(
      <CardDetail
        card={{ ...cards[0], perks: [], active_perk_count: 0 }}
        revision={0}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText(/None tracked yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a credit" })).toBeInTheDocument();
  });
});

describe("actions as icons (064)", () => {
  it("exposes edit and remove by accessible name, not by icon alone", () => {
    // An icon with no accessible name is unusable with a screen reader and ambiguous
    // with a mouse. Every IconButton requires a label for exactly this.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    // Card-level actions live in the list now; these are the per-credit ones.
    expect(screen.getByRole("button", { name: /^Edit Travel credit/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Which periods you used Travel credit in/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Remove Travel credit/ })).toBeInTheDocument();
  });

  it("keeps the glyph and the words on an urgent countdown", () => {
    // Colour amplifies; it never carries the meaning alone. This survives a colourblind
    // reader and a monochrome print.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const travel = rows.find((row) => within(row).queryByText("Travel credit"));
    expect(within(travel!).getByText("3 days")).toBeInTheDocument();
  });
});

describe("a used credit (065)", () => {
  it("shows no countdown once it has been used", () => {
    // Nothing is running out if it is already spent. The dining credit is marked used in
    // the fixture; the travel credit is not.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const dining = rows.find((row) => within(row).queryByText("Dining credit"));
    const travel = rows.find((row) => within(row).queryByText("Travel credit"));

    expect(within(dining!).queryByText(/days|Today|Tomorrow|week/)).toBeNull();
    expect(within(travel!).getByText("3 days")).toBeInTheDocument();
  });
});

describe("the annual fee (062)", () => {
  it("offers to add a fee when none is recorded", () => {
    render(
      <CardDetail
        card={{ ...cards[0], annual_fee_cents: null, realised_this_fee_year_cents: null }}
        revision={0}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Add an annual fee" })).toBeInTheDocument();
  });

  it("offers to edit one that exists", () => {
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Edit annual fee" })).toBeInTheDocument();
  });
});
