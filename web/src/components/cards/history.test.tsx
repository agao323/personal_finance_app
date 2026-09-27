import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HistoryPanel } from "@/components/cards/history";
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

    await userEvent.click(screen.getByRole("button", { name: "This quarter" }));

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

describe("HistoryPanel refreshing", () => {
  it("keeps the rows and totals up while a new window loads", async () => {
    // The complaint this fixes: switching window blanked the totals and the whole list and
    // rebuilt them, for a request that answers in a tenth of a second.
    // A holder rather than a bare `let`: TypeScript narrows a local assigned only inside
    // a closure to `null`, and the release call then fails to type-check.
    const gate: { release: (() => void) | null } = { release: null };
    render(<HistoryPanel revision={0} />);
    await screen.findByText("Dining credit");

    server.use(
      http.get("/api/cards/history", async () => {
        await new Promise<void>((resolve) => {
          gate.release = resolve;
        });
        return HttpResponse.json({ ...walletHistory, redemptions: [] });
      }),
    );
    // A window other than the one already selected; clicking the current one changes
    // nothing and would make this test pass without exercising anything.
    await userEvent.click(screen.getByRole("button", { name: "This quarter" }));

    await waitFor(() => expect(gate.release).not.toBeNull());
    expect(screen.getByText("Dining credit")).toBeInTheDocument();
    expect(screen.getByText("Refreshing")).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading")).not.toBeInTheDocument();

    gate.release?.();
    await waitFor(() => expect(screen.queryByText("Dining credit")).not.toBeInTheDocument());
  });

  it("keeps the figures when a refresh fails", async () => {
    render(<HistoryPanel revision={0} />);
    await screen.findByText("Dining credit");

    server.use(
      http.get("/api/cards/history", () => HttpResponse.json({ detail: "nope" }, { status: 500 })),
    );
    await userEvent.click(screen.getByRole("button", { name: "This quarter" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not refresh");
    expect(screen.getByText("Dining credit")).toBeInTheDocument();
  });
});

describe("windows that follow the cadences (071)", () => {
  it("asks for the calendar period, not a count of months back", async () => {
    // "This quarter" is the unit a quarterly credit is described in. "3 months back" is a
    // unit nothing is described in.
    const urls: string[] = [];
    server.use(
      http.get("/api/cards/history", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(walletHistory);
      }),
    );
    render(<HistoryPanel revision={0} />);
    await screen.findByText("Dining credit");

    await userEvent.click(screen.getByRole("button", { name: "This month" }));

    await waitFor(() => expect(urls).toHaveLength(2));
    const now = new Date();
    const firstOfMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
      .toISOString()
      .slice(0, 10);
    expect(new URL(urls[1]).searchParams.get("from")).toBe(firstOfMonth);
  });

  it("offers every cadence's own period", async () => {
    render(<HistoryPanel revision={0} />);

    for (const label of ["This month", "This quarter", "This half year", "This year", "All time"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("splits realised value by cadence, and the split sums to the total", async () => {
    // One number covering a monthly dining credit and an annual travel credit describes
    // neither.
    render(<HistoryPanel revision={0} />);

    await screen.findByText("Dining credit");
    const monthly = screen.getByText("Monthly").parentElement;
    const annual = screen.getByText("Annual").parentElement;
    expect(monthly).toHaveTextContent("$25.00");
    expect(annual).toHaveTextContent("$300.00");
    // $25 + $300 is the $325 the panel reports realised.
    expect(screen.getByText("$325.00")).toBeInTheDocument();
  });

  it("omits a cadence with nothing in the window rather than showing it as zero", async () => {
    server.use(
      http.get("/api/cards/history", () =>
        HttpResponse.json({
          ...walletHistory,
          redemptions: walletHistory.redemptions.filter((row) => row.cadence === "monthly"),
        }),
      ),
    );
    render(<HistoryPanel revision={0} />);

    await screen.findByText("Dining credit");
    expect(screen.queryByText("Quarterly")).not.toBeInTheDocument();
    // And with only one cadence left there is no breakdown at all — it would be the total
    // written twice.
    expect(screen.queryByText("Monthly")).not.toBeInTheDocument();
  });

  it("says the window is about the period a credit belongs to", async () => {
    // Nothing records the day you spent it, so a window claiming otherwise would claim a
    // precision the rows do not have.
    render(<HistoryPanel revision={0} />);

    expect(screen.getByText(/not the day you spent it/)).toBeInTheDocument();
  });
});
