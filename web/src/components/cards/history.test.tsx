import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackfillForm, HistoryPanel } from "@/components/cards/history";
import { mockCards, server, walletHistory } from "@/test/msw";

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("HistoryPanel", () => {
  it("asks for everything by default, with no window", async () => {
    // "Show me the whole history" is the request. A silent cut-off would hide exactly
    // the old entries being asked for.
    const urls: string[] = [];
    server.use(
      http.get("/api/cards/history", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(walletHistory);
      }),
    );

    render(<HistoryPanel revision={0} />);

    await waitFor(() => expect(urls).toHaveLength(1));
    expect(new URL(urls[0]).searchParams.get("from")).toBeNull();
    expect(screen.getByRole("button", { name: "All time" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("lists entries newest first, across cards", async () => {
    render(<HistoryPanel revision={0} />);

    await screen.findByText("Dining credit");
    const names = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(names[0]).toContain("Dining credit");
    expect(names[1]).toContain("Travel credit");
  });

  it("reports what was realised and how many periods went unused", async () => {
    // The second number is the one that changes behaviour.
    render(<HistoryPanel revision={0} />);

    expect(await screen.findByText("$325.00")).toBeInTheDocument();
    expect(screen.getByText(/4/)).toBeInTheDocument();
    expect(screen.getByText(/periods went unused/)).toBeInTheDocument();
  });

  it("distinguishes a recorded amount from an inferred full value", async () => {
    // "Used it all" and "used exactly this much" are different facts.
    render(<HistoryPanel revision={0} />);

    await screen.findByText("Dining credit");
    expect(screen.getByText("full")).toBeInTheDocument();
  });

  it("narrows to a window when asked", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/cards/history", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(walletHistory);
      }),
    );

    render(<HistoryPanel revision={0} />);
    await waitFor(() => expect(urls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "3 months" }));

    await waitFor(() => expect(urls).toHaveLength(2));
    expect(new URL(urls[1]).searchParams.get("from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("says so when nothing has been recorded", async () => {
    server.use(
      http.get("/api/cards/history", () =>
        HttpResponse.json({
          ...walletHistory,
          realised_cents: 0,
          missed_periods: 0,
          redemptions: [],
        }),
      ),
    );

    render(<HistoryPanel revision={0} />);

    expect(await screen.findByText(/Nothing recorded yet/)).toBeInTheDocument();
  });
});

describe("BackfillForm", () => {
  it("records a past use by naming a date inside the period", async () => {
    const onDone = vi.fn();
    render(<BackfillForm perkId={1} onDone={onDone} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Record a past use"), "2026-03-15");
    await userEvent.click(screen.getByRole("button", { name: "Record" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("refuses to submit with no date", async () => {
    render(<BackfillForm perkId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Record" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Pick a date/);
  });

  it("surfaces the API's refusal for a date before the credit existed", async () => {
    // The period arithmetic lives in the service. The browser does not guess at it and
    // does not paraphrase its refusal.
    server.use(
      http.post("/api/perks/:id/redemptions", () =>
        HttpResponse.json(
          { detail: "That date is before this perk's first period" },
          { status: 422 },
        ),
      ),
    );
    render(<BackfillForm perkId={1} onDone={() => {}} onCancel={() => {}} />);

    await userEvent.type(screen.getByLabelText("Record a past use"), "2020-01-01");
    await userEvent.click(screen.getByRole("button", { name: "Record" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/before this perk's first period/);
  });

  it("explains that the period is worked out from the credit's schedule", () => {
    // "2 March" landing in the February period of a month-end anchor is surprising.
    render(<BackfillForm perkId={1} onDone={() => {}} onCancel={() => {}} />);

    expect(screen.getByText(/worked out from the credit/)).toBeInTheDocument();
  });
});
