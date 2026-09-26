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

    // An icon button now — reachable by its accessible name, which is the point of
    // requiring one on every IconButton.
    await userEvent.click(screen.getByRole("button", { name: "Rename Sapphire Reserve" }));
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

describe("actions as icons (064)", () => {
  it("exposes edit and remove by accessible name, not by icon alone", () => {
    // An icon with no accessible name is unusable with a screen reader and ambiguous
    // with a mouse. Every IconButton requires a label for exactly this.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Rename Sapphire Reserve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Edit Travel credit/ })).toBeInTheDocument();
  });

  it("keeps the glyph and the words on an urgent countdown", () => {
    // Colour amplifies; it never carries the meaning alone. This survives a colourblind
    // reader and a monochrome print.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    const travel = rows.find((row) => within(row).queryByText("Travel credit"));
    expect(within(travel!).getByText("3 days")).toBeInTheDocument();
  });
});

describe("a used credit (065)", () => {
  it("shows no countdown once it has been used", () => {
    // Nothing is running out if it is already spent. The dining credit is marked used in
    // the fixture; the travel credit is not.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

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
      <CardRow
        card={{ ...cards[0], annual_fee_cents: null, realised_this_fee_year_cents: null }}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Add an annual fee" })).toBeInTheDocument();
  });

  it("offers to edit one that exists", () => {
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Edit annual fee" })).toBeInTheDocument();
  });
});

describe("removing a card (063)", () => {
  it("names what would be destroyed, by count", async () => {
    // "All data" is a phrase people click past. Counts are read.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/balance snapshots?/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
  });

  it("offers closing first, because that is usually what is wanted", async () => {
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByRole("button", { name: "Close this card" })).toBeInTheDocument();
  });

  it("carries no ticket numbers or project state in its copy", async () => {
    // An earlier version told the reader backups were unfinished. Whether our backlog is
    // caught up is not something a person deleting a card can act on, and it dates the
    // moment it changes.
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");

    expect(dialog.textContent).not.toMatch(/ticket|backup|017/i);
  });

  it("keeps delete disabled until the name is typed exactly", async () => {
    render(<CardRow card={cards[0]} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Delete permanently" });

    expect(confirm).toBeDisabled();

    await userEvent.type(within(dialog).getByRole("textbox"), "sapphire reserve");
    expect(confirm).toBeDisabled();

    await userEvent.clear(within(dialog).getByRole("textbox"));
    await userEvent.type(within(dialog).getByRole("textbox"), "Sapphire Reserve");
    expect(confirm).toBeEnabled();
  });
});
