import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CardDetail } from "@/components/cards/card-detail";
import { cards, mockCards } from "@/test/msw";
import { expiryLabel } from "@/components/cards/types";

const pushed = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushed }) }));

beforeEach(() => {
  pushed.mockClear();
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

describe("the annual fee (062, 072)", () => {
  it("offers to add a fee when none is recorded", () => {
    render(
      <CardDetail
        card={{ ...cards[0], annual_fee_cents: null, realised_this_fee_year_cents: null }}
        revision={0}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("puts the control with the figure it edits, not in the panel header", async () => {
    // A control somewhere other than the thing it acts on is a control you have to look
    // for. Asserted structurally, because "next to" is the whole point.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    const figure = screen.getByText("Annual fee").parentElement;
    expect(within(figure!).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(figure!).getByText("$695.00")).toBeInTheDocument();
  });

  it("keeps the figures visible while the fee is being edited", async () => {
    // Ticket 070's rule: nothing that is still true gets unmounted.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByText("Realised this fee year")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save fee" })).toBeInTheDocument();
  });
});

describe("acting on the card (072)", () => {
  it("renames the card from its own header", async () => {
    const onChange = vi.fn();
    render(<CardDetail card={cards[0]} revision={0} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Rename Sapphire Reserve" }));
    const field = screen.getByLabelText("Card name");
    await userEvent.clear(field);
    await userEvent.type(field, "Sapphire");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("warns what deleting takes with it, in the card's own panel", async () => {
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));

    expect(await screen.findByText(/312/)).toBeInTheDocument();
  });

  it("carries no ticket numbers or project state in the deletion copy", async () => {
    // An earlier version told the reader backups were unfinished. Whether our backlog is
    // caught up is not something a person deleting a card can act on.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");

    expect(dialog.textContent).not.toMatch(/ticket|backup|017/i);
  });

  it("offers closing the card before deleting it", async () => {
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");

    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close this card" })).toBeInTheDocument();
  });

  it("keeps delete disabled until the name is typed exactly", async () => {
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Delete permanently" });

    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Sapphire Reserve");
    expect(confirm).toBeEnabled();
  });

  it("leaves the card's page once the card is gone", async () => {
    // Staying would render "No such card" — a dead end the reader's own action put them in.
    render(<CardDetail card={cards[0]} revision={0} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    await screen.findByText(/312/);
    await userEvent.type(screen.getByLabelText(/To delete it anyway/i), "Sapphire Reserve");
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));

    await waitFor(() => expect(pushed).toHaveBeenCalledWith("/cards"));
  });
});
