import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CardList } from "@/components/cards/card-list";
import { cards, mockCards } from "@/test/msw";

const two = [
  cards[0],
  { ...cards[0], account_id: 2, name: "Freedom Unlimited", institution: "Chase", perks: [] },
];

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("CardList", () => {
  it("is one compact row per card, so ten cards is ten lines", () => {
    render(<CardList cards={two} onChange={() => {}} />);

    // Two cards plus the Overview row above them.
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("always offers a way back to the cross-card view", () => {
    // Without this the only route out of a card was editing the URL.
    render(<CardList cards={two} selectedId={1} onChange={() => {}} />);

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/cards");
  });

  it("marks Overview as current when no card is selected", () => {
    render(<CardList cards={two} onChange={() => {}} />);

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  });

  it("links each card to its own URL rather than filtering in place", () => {
    // Navigation, not filtering — that is what makes the back button and a bookmark work.
    render(<CardList cards={two} onChange={() => {}} />);

    expect(screen.getByRole("link", { name: /Sapphire Reserve/ })).toHaveAttribute(
      "href",
      "/cards/1",
    );
  });

  it("marks the selected card for assistive tech, not just visually", () => {
    render(<CardList cards={two} selectedId={2} onChange={() => {}} />);

    expect(screen.getByRole("link", { name: /Freedom Unlimited/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("flags a card with something running out", () => {
    render(<CardList cards={two} onChange={() => {}} />);

    const rows = screen.getAllByRole("listitem");
    // rows[0] is Overview; the Sapphire has an urgent unused credit, the other has none.
    expect(within(rows[1]).getByTitle(/running out/)).toBeInTheDocument();
    expect(within(rows[2]).queryByTitle(/running out/)).toBeNull();
  });

  it("adds a card in card language, without mentioning accounts", async () => {
    // The list used to say "a card is an account with the credit card subtype" and link
    // to a form that only reaches a card after you pick "liability" as the Kind.
    render(<CardList cards={two} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Add a card" }));

    expect(screen.getByLabelText("Card name")).toBeInTheDocument();
    expect(screen.getByLabelText("Issuer")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/subtype|liability/i);
  });

  it("creates the card and tells the list to refresh", async () => {
    const onChange = vi.fn();
    render(<CardList cards={two} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Add a card" }));
    await userEvent.type(screen.getByLabelText("Card name"), "Gold");
    await userEvent.click(screen.getByRole("button", { name: "Add card" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("still offers adding when there are no cards at all", () => {
    render(<CardList cards={[]} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Add a card" })).toBeInTheDocument();
  });
});

describe("managing a card from the list", () => {
  it("renames in place", async () => {
    const onChange = vi.fn();
    render(<CardList cards={two} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Rename Sapphire Reserve" }));
    const field = screen.getByLabelText("Card name");
    await userEvent.clear(field);
    await userEvent.type(field, "Platinum");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("puts a button inside the row rather than inside the link", () => {
    // A button nested in an anchor is invalid HTML and behaves unpredictably for keyboard
    // and screen-reader users. The row is a flex container; the link and the buttons are
    // siblings.
    render(<CardList cards={two} onChange={() => {}} />);

    const link = screen.getByRole("link", { name: /Sapphire Reserve/ });
    expect(link.querySelector("button")).toBeNull();
  });

  it("opens the deletion dialog from the list", async () => {
    render(<CardList cards={two} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Close this card" })).toBeInTheDocument();
  });

  it("carries no ticket numbers or project state in the deletion copy", async () => {
    // An earlier version told the reader backups were unfinished. Whether our backlog is
    // caught up is not something a person deleting a card can act on.
    render(<CardList cards={two} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");

    expect(dialog.textContent).not.toMatch(/ticket|backup|017/i);
  });

  it("keeps delete disabled until the name is typed exactly", async () => {
    render(<CardList cards={two} onChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /^Delete Sapphire Reserve/ }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Delete permanently" });

    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Sapphire Reserve");
    expect(confirm).toBeEnabled();
  });
});
