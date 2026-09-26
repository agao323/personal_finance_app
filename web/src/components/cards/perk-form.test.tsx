import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PerkForm, PerkRemoveButton } from "@/components/cards/perk-form";
import { cards, mockCards } from "@/test/msw";

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("PerkForm", () => {
  it("adds a credit", async () => {
    const onDone = vi.fn();
    render(<PerkForm accountId={1} onDone={onDone} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Name"), "Lounge access");
    await userEvent.type(screen.getByLabelText("Value"), "200");
    await userEvent.type(screen.getByLabelText("First period began"), "2026-01-01");
    await userEvent.click(screen.getByRole("button", { name: "Add credit" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("prefills when editing and saves the change", async () => {
    const onDone = vi.fn();
    render(<PerkForm accountId={1} perk={cards[0].perks[0]} onDone={onDone} onCancel={() => {}} />);

    expect(screen.getByLabelText("Name")).toHaveValue("Travel credit");
    expect(screen.getByLabelText("Value")).toHaveValue("300.00");

    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.type(screen.getByLabelText("Name"), "Travel credit (renamed)");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("refuses a credit with no value", async () => {
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Name"), "Lounge");
    await userEvent.click(screen.getByRole("button", { name: "Add credit" }));

    expect(await screen.findByText(/what the credit is worth/)).toBeInTheDocument();
  });

  it("refuses a credit with no anchor date", async () => {
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Name"), "Lounge");
    await userEvent.type(screen.getByLabelText("Value"), "200");
    await userEvent.click(screen.getByRole("button", { name: "Add credit" }));

    // Matched on the error sentence, not the label — a looser regex hits both.
    expect(await screen.findByText(/Enter the date this credit/)).toBeInTheDocument();
  });

  it("explains the anchor date, because the label alone does not", () => {
    // The field most likely to be filled in wrong, and a wrong value silently shifts
    // every period for that credit.
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    expect(screen.getByText(/cardmember year/)).toBeInTheDocument();
  });

  it("warns that history keeps its recorded periods when the schedule changes", async () => {
    render(
      <PerkForm accountId={1} perk={cards[0].perks[0]} onDone={() => {}} onCancel={() => {}} />,
    );

    await userEvent.selectOptions(screen.getByLabelText("Resets"), "monthly");

    expect(screen.getByText(/keeps the periods it was recorded against/)).toBeInTheDocument();
  });
});

describe("PerkRemoveButton", () => {
  it("confirms before removing", async () => {
    render(<PerkRemoveButton perk={cards[0].perks[1]} onDone={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(screen.getByText("Remove permanently?")).toBeInTheDocument();
  });

  it("removes a credit with no history", async () => {
    const onDone = vi.fn();
    render(<PerkRemoveButton perk={cards[0].perks[1]} onDone={onDone} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("offers retire when the API refuses because the credit has history", async () => {
    // Delete and retire look alike and are different actions. The refusal shows the
    // API's own message rather than a local paraphrase that could drift from the rule.
    render(<PerkRemoveButton perk={cards[0].perks[0]} onDone={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/3 recorded uses/);
    expect(screen.getByRole("button", { name: "Retire instead" })).toBeInTheDocument();
  });

  it("offers to un-retire a retired credit", () => {
    render(
      <PerkRemoveButton perk={{ ...cards[0].perks[0], is_active: false }} onDone={() => {}} />,
    );

    expect(screen.getByRole("button", { name: "Un-retire" })).toBeInTheDocument();
  });
});
