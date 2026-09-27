import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PerkForm, PerkRemoveButton } from "@/components/cards/perk-form";
import { cards, mockCards, server } from "@/test/msw";

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
    // No anchor typed: calendar boundaries are the default (ticket 079).
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

  it("refuses a custom schedule with the date cleared", async () => {
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Name"), "Lounge");
    await userEvent.type(screen.getByLabelText("Value"), "200");
    await userEvent.click(screen.getByLabelText("A different date"));
    await userEvent.clear(screen.getByLabelText("Date it resets on"));
    await userEvent.click(screen.getByRole("button", { name: "Add credit" }));

    // Matched on the error sentence, not the label — a looser regex hits both.
    expect(await screen.findByText(/Enter a date one of this credit/)).toBeInTheDocument();
  });

  it("says a custom date is for a cardmember-year credit", () => {
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

describe("calendar boundaries by default (079)", () => {
  it("defaults to the calendar schedule for the chosen cadence", async () => {
    // A quarterly credit means Jan, Apr, Jul, Oct. Getting anything else now takes saying so.
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.selectOptions(screen.getByLabelText("Resets"), "quarterly");

    expect(screen.getByLabelText("Calendar quarters")).toBeChecked();
    expect(screen.queryByLabelText("Date it resets on")).not.toBeInTheDocument();
  });

  it("sends 1 January as the anchor when the calendar schedule is chosen", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/cards/:id/perks", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ id: 99 }, { status: 201 });
      }),
    );
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Name"), "Lounge");
    await userEvent.type(screen.getByLabelText("Value"), "50");
    await userEvent.selectOptions(screen.getByLabelText("Resets"), "quarterly");
    await userEvent.click(screen.getByRole("button", { name: "Add credit" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    const year = new Date().getUTCFullYear();
    expect(bodies[0]).toMatchObject({ cadence: "quarterly", anchor_on: `${year}-01-01` });
  });

  it("reveals the date input only when a different date is chosen", async () => {
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.click(screen.getByLabelText("A different date"));

    expect(screen.getByLabelText("Date it resets on")).toBeInTheDocument();
  });

  it("shows the reset dates the API works out, not dates computed here", async () => {
    // The consequence of an anchor was invisible until after saving, which is how a
    // quarterly credit came to reset in December.
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    expect(await screen.findByText(/^Resets Oct 1, 2026, Jan 1, 2027/)).toBeInTheDocument();
  });

  it("says plainly when an anchor is not on calendar boundaries", async () => {
    server.use(
      http.get("/api/perks/schedule", () =>
        HttpResponse.json({
          cadence: "quarterly",
          anchor_on: "2026-09-01",
          is_calendar_aligned: false,
          current_start: "2026-09-01",
          resets_on: ["2026-12-01", "2027-03-01", "2027-06-01", "2027-09-01"],
        }),
      ),
    );
    render(<PerkForm accountId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.selectOptions(screen.getByLabelText("Resets"), "quarterly");

    expect(await screen.findByText(/not calendar quarters/)).toBeInTheDocument();
  });
});

describe("PerkRemoveButton", () => {
  it("confirms before removing", async () => {
    render(<PerkRemoveButton perk={cards[0].perks[1]} onDone={() => {}} />);

    await userEvent.click(
      screen.getByRole("button", { name: /^Remove Travel credit|^Remove Dining credit/ }),
    );

    expect(screen.getByText("Remove permanently?")).toBeInTheDocument();
  });

  it("removes a credit with no history", async () => {
    const onDone = vi.fn();
    render(<PerkRemoveButton perk={cards[0].perks[1]} onDone={onDone} />);

    await userEvent.click(
      screen.getByRole("button", { name: /^Remove Travel credit|^Remove Dining credit/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("offers retire when the API refuses because the credit has history", async () => {
    // Delete and retire look alike and are different actions. The refusal shows the
    // API's own message rather than a local paraphrase that could drift from the rule.
    render(<PerkRemoveButton perk={cards[0].perks[0]} onDone={() => {}} />);

    await userEvent.click(
      screen.getByRole("button", { name: /^Remove Travel credit|^Remove Dining credit/ }),
    );
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
