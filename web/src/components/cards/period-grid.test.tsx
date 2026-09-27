/**
 * Marking periods, not dates. (Ticket 069)
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PeriodGrid } from "@/components/cards/period-grid";
import { cards, mockCards, server } from "@/test/msw";

const perk = cards[0].perks[1];

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

/** Three named months, so a test can assert on an exact date rather than a shape. */
const THREE_MONTHS = {
  perk_id: perk.id,
  cadence: "monthly" as const,
  anchor_on: "2026-03-01",
  has_earlier: false,
  periods: [
    { start: "2026-03-01", end: "2026-04-01", index: 0 },
    { start: "2026-04-01", end: "2026-05-01", index: 1 },
    { start: "2026-05-01", end: "2026-06-01", index: 2 },
  ].map((period, order) => ({
    ...period,
    is_used: false,
    used_amount_cents: null,
    note: null,
    is_current: order === 2,
  })),
};

/** The chips, in render order. Only the period toggles carry `aria-pressed`. */
function chips() {
  return screen.getAllByRole("button").filter((button) => button.hasAttribute("aria-pressed"));
}

describe("PeriodGrid", () => {
  it("offers one chip per period, oldest first, with the current one last", async () => {
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    await waitFor(() => expect(chips()).toHaveLength(6));
    expect(chips().at(-1)?.textContent).toContain("now");
  });

  it("carries the exact period in each chip's accessible name", async () => {
    // The label names a calendar month. A perk anchored mid-month has periods that are not
    // calendar months, so the range is what the chip actually promises.
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    await waitFor(() => expect(chips()).toHaveLength(6));
    expect(chips()[0].getAttribute("aria-label")).toMatch(/not used\. The period from .*, resets /);
  });

  it("marks the period the chip names, not today", async () => {
    // The contract with `mark_used`: the period's own start is a date inside it, so the
    // server resolves it to that period. The reader never sees a date at all.
    const posted: unknown[] = [];
    server.use(
      http.get("/api/perks/:id/periods", () => HttpResponse.json(THREE_MONTHS)),
      http.post("/api/perks/:id/redemptions", async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json(perk);
      }),
    );
    const onChange = vi.fn();
    render(<PeriodGrid perk={perk} revision={0} onChange={onChange} />);

    await userEvent.click(await screen.findByRole("button", { name: /Apr 2026/ }));

    await waitFor(() => expect(posted).toEqual([{ on: "2026-04-01" }]));
    expect(onChange).toHaveBeenCalled();
  });

  it("flips the chip immediately rather than waiting for the round trip", async () => {
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    await waitFor(() => expect(chips()).toHaveLength(6));
    const target = chips()[0];
    await userEvent.click(target);

    // Not after a round trip: the same tick.
    expect(target).toHaveAttribute("aria-pressed", "true");
  });

  it("unmarks the period the chip names", async () => {
    const deleted: string[] = [];
    server.use(
      http.get("/api/perks/:id/periods", () =>
        HttpResponse.json({
          ...THREE_MONTHS,
          periods: THREE_MONTHS.periods.map((period) =>
            period.start === "2026-04-01" ? { ...period, is_used: true } : period,
          ),
        }),
      ),
      http.delete("/api/perks/:id/redemptions", ({ request }) => {
        deleted.push(new URL(request.url).searchParams.get("on") ?? "");
        return HttpResponse.json(perk);
      }),
    );
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    const target = await screen.findByRole("button", { name: /Apr 2026/ });
    expect(target).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(target);

    await waitFor(() => expect(deleted).toEqual(["2026-04-01"]));
  });

  it("puts a failed toggle back and says nothing was saved", async () => {
    server.use(
      http.post("/api/perks/:id/redemptions", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    await waitFor(() => expect(chips()).toHaveLength(6));
    const target = chips()[0];
    await userEvent.click(target);

    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    expect(target).toHaveAttribute("aria-pressed", "false");
  });

  it("asks for more periods when you ask for earlier ones", async () => {
    const asked: number[] = [];
    server.use(
      http.get("/api/perks/:id/periods", ({ request }) => {
        const back = Number(new URL(request.url).searchParams.get("back"));
        asked.push(back);
        return HttpResponse.json({
          perk_id: perk.id,
          cadence: "monthly",
          anchor_on: "2020-01-01",
          has_earlier: true,
          periods: [
            {
              start: "2026-06-01",
              end: "2026-07-01",
              index: 77,
              is_used: false,
              used_amount_cents: null,
              note: null,
              is_current: true,
            },
          ],
        });
      }),
    );
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    await screen.findByRole("button", { name: /Jun 2026/ });
    await userEvent.click(screen.getByRole("button", { name: "Show earlier" }));

    // A monthly credit starts at a year of history and asks for another on request.
    await waitFor(() => expect(asked).toEqual([12, 24]));
  });

  it("says so when the credit has no periods yet rather than showing an empty grid", async () => {
    server.use(
      http.get("/api/perks/:id/periods", () =>
        HttpResponse.json({
          perk_id: perk.id,
          cadence: "monthly",
          anchor_on: "2030-01-01",
          has_earlier: false,
          periods: [],
        }),
      ),
    );
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    expect(await screen.findByText(/first period has not begun/)).toBeInTheDocument();
  });

  it("shows a recorded partial amount on the chip", async () => {
    // "Used it all" and "used $12 of it" are different facts and a filled chip alone
    // flattens them.
    server.use(
      http.get("/api/perks/:id/periods", () =>
        HttpResponse.json({
          perk_id: perk.id,
          cadence: "monthly",
          anchor_on: "2026-01-01",
          has_earlier: false,
          periods: [
            {
              start: "2026-05-01",
              end: "2026-06-01",
              index: 4,
              is_used: true,
              used_amount_cents: 1_200,
              note: null,
              is_current: false,
            },
          ],
        }),
      ),
    );
    render(<PeriodGrid perk={perk} revision={0} onChange={() => {}} />);

    expect(await screen.findByText("$12.00")).toBeInTheDocument();
  });
});

describe("naming the period", () => {
  it("calls a quarterly credit's periods quarters, not months", async () => {
    // "Tap a month" is wrong on a quarterly credit, and "tap a period" is a word nobody
    // uses about their own credit card.
    server.use(
      http.get("/api/perks/:id/periods", () =>
        HttpResponse.json({
          perk_id: perk.id,
          cadence: "quarterly",
          anchor_on: "2026-01-01",
          has_earlier: false,
          periods: [
            {
              start: "2026-07-01",
              end: "2026-10-01",
              index: 2,
              is_used: false,
              used_amount_cents: null,
              note: null,
              is_current: true,
            },
          ],
        }),
      ),
    );
    render(
      <PeriodGrid perk={{ ...perk, cadence: "quarterly" }} revision={0} onChange={() => {}} />,
    );

    expect(await screen.findByText(/Which quarters did you use this in\?/)).toBeInTheDocument();
    expect(screen.getByText(/for that quarter/)).toBeInTheDocument();
  });
});
