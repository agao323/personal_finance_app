import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { NetWorthChart, axisTicks, niceStep, tickIndices, yScale } from "./net-worth-chart";
import { rangeQuery } from "./range-selector";
import { formatCurrency, formatDate } from "@/lib/format";
import { mockNetWorthSeries, netWorthSeries, server } from "@/test/msw";

const POINTS = netWorthSeries.points;
const LATEST = POINTS[POINTS.length - 1];
const PREVIOUS = POINTS[POINTS.length - 2];

/** The chart is on screen once its as-of line is, which needs a resolved fetch. */
async function loaded(point = LATEST) {
  return screen.findByText(`as of ${formatDate(point.as_of)}`);
}

function tableRows(): number {
  // Minus the header row.
  return within(screen.getByRole("table")).getAllByRole("row").length - 1;
}

describe("rangeQuery", () => {
  const today = new Date("2026-08-18T00:00:00Z");

  it("maps each preset to a from-date and a matching interval", () => {
    expect(rangeQuery("3M", today)).toEqual({ from: "2026-05-18", interval: "day" });
    expect(rangeQuery("6M", today)).toEqual({ from: "2026-02-18", interval: "week" });
    expect(rangeQuery("1Y", today)).toEqual({ from: "2025-08-18", interval: "week" });
    expect(rangeQuery("YTD", today)).toEqual({ from: "2026-01-01", interval: "week" });
  });

  it("asks for everything, not for an empty from, on All", () => {
    expect(rangeQuery("ALL", today)).toEqual({ from: null, interval: "month" });
  });

  it("clamps the day of month instead of rolling it forward", () => {
    // Three months before 31 May is 28 February. Date arithmetic that overflows
    // would answer 3 March and quietly shorten the range.
    expect(rangeQuery("3M", new Date("2026-05-31T00:00:00Z")).from).toBe("2026-02-28");
  });

  it("works in UTC, so a range boundary does not shift by timezone", () => {
    expect(rangeQuery("YTD", new Date("2026-01-01T00:30:00Z")).from).toBe("2026-01-01");
  });
});

describe("chart scales", () => {
  it("keeps every tick an integer number of cents", () => {
    // A fractional tick means something divided by 100; formatCurrency rejects it.
    expect(yScale([1_234_567, 9_876_543]).ticks.every(Number.isInteger)).toBe(true);
    expect(Number.isInteger(niceStep(1_234_567))).toBe(true);
  });

  it("always spans zero, so the area is measured from a real baseline", () => {
    expect(yScale([11_820_000, 15_252_000]).min).toBe(0);
    expect(yScale([-4_000_000, -1_000_000]).max).toBe(0);

    // A history that crosses zero keeps both extremes inside the domain and puts a
    // gridline on zero itself, which is the line the reader is actually looking for.
    const crossing = yScale([-4_000_000, 6_000_000]);
    expect(crossing.min).toBeLessThanOrEqual(-4_000_000);
    expect(crossing.max).toBeGreaterThanOrEqual(6_000_000);
    expect(crossing.ticks).toContain(0);
  });

  it("gives a flat all-zero history an axis to sit on", () => {
    const scale = yScale([0, 0, 0]);
    expect(scale.max).toBeGreaterThan(scale.min);
    expect(scale.ticks.length).toBeGreaterThan(1);
  });

  it("always labels the first and last point", () => {
    expect(tickIndices(3)).toEqual([0, 1, 2]);
    const spread = tickIndices(40);
    expect(spread).toHaveLength(5);
    expect(spread[0]).toBe(0);
    expect(spread[spread.length - 1]).toBe(39);
  });

  it("drops an axis label rather than printing it over its neighbour", () => {
    // Two snapshots close together at the start of a long sparse history: evenly
    // spread indices put their labels a few pixels apart.
    expect(axisTicks([64, 89, 480, 702])).toEqual([0, 2, 3]);
    // Comfortably spaced points all keep their labels.
    expect(axisTicks([64, 224, 384, 544, 702])).toEqual([0, 1, 2, 3, 4]);
    // The last point is the range's end; a crowded neighbour yields to it.
    expect(axisTicks([64, 300, 690, 702])).toEqual([0, 1, 3]);
    expect(axisTicks([350])).toEqual([0]);
  });
});

describe("net worth chart", () => {
  it("leads with the latest ownership-adjusted value", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    const summary = screen.getByRole("list", { name: "Latest values" });
    expect(within(summary).getByText(formatCurrency(LATEST.net_worth_cents))).toBeInTheDocument();
  });

  it("names the scope so a household number is never mistaken for a personal one", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="household" />);

    expect(await screen.findByText("Household net worth over time")).toBeInTheDocument();
  });

  it("puts every plotted value in a table, so the tooltip is never the only way to read one", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    const table = within(screen.getByRole("table"));
    expect(table.getByText(formatCurrency(LATEST.assets_cents))).toBeInTheDocument();
    expect(table.getByText(formatCurrency(LATEST.liabilities_cents))).toBeInTheDocument();
  });
});

describe("range switching", () => {
  it("plots a wider window on All and a narrower one on 3M", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();
    const oneYear = tableRows();

    await userEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(tableRows()).toBe(POINTS.length));
    expect(POINTS.length).toBeGreaterThan(oneYear);

    await userEvent.click(screen.getByRole("button", { name: "3M" }));
    await waitFor(() => expect(tableRows()).toBeLessThan(oneYear));
  });

  it("sends the selected range and scope to the API", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/net-worth/series", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(netWorthSeries);
      }),
    );

    render(<NetWorthChart view="household" />);
    await loaded();

    await userEvent.click(screen.getByRole("button", { name: "3M" }));
    await waitFor(() => expect(urls).toHaveLength(2));

    const params = new URL(urls[1]).searchParams;
    expect(params.get("view")).toBe("household");
    expect(params.get("interval")).toBe("day");
    expect(params.get("from")).toBe(rangeQuery("3M").from);
  });

  it("does not refetch a range it has already loaded", async () => {
    // Ticket 052. Switching 1Y → 3M → 1Y used to be three round trips for two
    // distinct answers, and the third had a loading state in front of data the
    // client already held.
    const urls: string[] = [];
    server.use(
      http.get("/api/net-worth/series", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(netWorthSeries);
      }),
    );

    render(<NetWorthChart view="mine" />);
    await loaded();
    expect(urls).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "3M" }));
    await waitFor(() => expect(urls).toHaveLength(2));

    await userEvent.click(screen.getByRole("button", { name: "1Y" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "true"),
    );

    // Still two: the return trip to 1Y was served from the cache.
    expect(urls).toHaveLength(2);
  });

  it("shows the cached data immediately, with no loading state", async () => {
    // The point of the cache. If it re-rendered an empty chart first, the flicker
    // would make it feel slower than the refetch it replaced.
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();
    const initialRows = tableRows();

    await userEvent.click(screen.getByRole("button", { name: "3M" }));
    await waitFor(() => expect(tableRows()).toBeGreaterThan(0));

    await userEvent.click(screen.getByRole("button", { name: "1Y" }));

    // Synchronously after the click, without awaiting anything.
    expect(tableRows()).toBe(initialRows);
  });

  it("marks the selected range", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "YTD" }));

    expect(screen.getByRole("button", { name: "YTD" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("empty and single-point history", () => {
  it("says there is no history rather than drawing an empty frame", async () => {
    mockNetWorthSeries({ points: [] });

    render(<NetWorthChart view="mine" />);

    expect(await screen.findByText("No history yet")).toBeInTheDocument();
    // Nothing to plot is not a broken card: the controls stay usable, because a
    // longer range is the fix a reader will reach for.
    expect(screen.getByRole("group", { name: "Time range" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("points at a longer range when this one is simply empty", async () => {
    mockNetWorthSeries({ points: [] });

    render(<NetWorthChart view="mine" />);
    await screen.findByText("No history yet");

    expect(screen.getByText(/Try a longer range/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "All" }));

    // On All there is no longer range to suggest, so it stops suggesting one.
    await waitFor(() => expect(screen.queryByText(/Try a longer range/)).not.toBeInTheDocument());
  });

  it("draws day one as one deliberate point, not a broken line", async () => {
    mockNetWorthSeries({ points: [LATEST] });

    render(<NetWorthChart view="mine" />);
    await loaded();

    expect(screen.getByText(/One snapshot so far/)).toBeInTheDocument();

    const summary = screen.getByRole("list", { name: "Latest values" });
    expect(within(summary).getByText(formatCurrency(LATEST.net_worth_cents))).toBeInTheDocument();
    expect(tableRows()).toBe(1);
  });

  it("still reads out the single point on keyboard focus", async () => {
    mockNetWorthSeries({ points: [LATEST] });

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("group", { name: /arrow keys/i }));

    const readout = within(screen.getByRole("status", { name: "Chart readout" }));
    expect(readout.getByText(formatCurrency(LATEST.net_worth_cents))).toBeInTheDocument();
  });
});

describe("tooltip", () => {
  it("reads out the focused point without a mouse", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    const plot = screen.getByRole("group", { name: /arrow keys/i });
    expect(screen.getByRole("status", { name: "Chart readout" })).toBeEmptyDOMElement();

    // Focus lands on the most recent point — the one the reader was already looking at.
    await userEvent.click(plot);

    const readout = within(screen.getByRole("status", { name: "Chart readout" }));
    expect(readout.getByText(formatDate(LATEST.as_of))).toBeInTheDocument();
    expect(readout.getByText(formatCurrency(LATEST.net_worth_cents))).toBeInTheDocument();
    expect(readout.getByText("Net worth")).toBeInTheDocument();
  });

  it("walks the series with the arrow keys", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("group", { name: /arrow keys/i }));
    await userEvent.keyboard("{ArrowLeft}");

    const readout = within(screen.getByRole("status", { name: "Chart readout" }));
    expect(readout.getByText(formatDate(PREVIOUS.as_of))).toBeInTheDocument();
    expect(readout.getByText(formatCurrency(PREVIOUS.net_worth_cents))).toBeInTheDocument();
  });

  it("stops at the ends instead of running off the series", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("group", { name: /arrow keys/i }));
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");

    const readout = within(screen.getByRole("status", { name: "Chart readout" }));
    expect(readout.getByText(formatDate(LATEST.as_of))).toBeInTheDocument();

    await userEvent.keyboard("{Home}");
    const earliest = POINTS.filter((point) => point.as_of >= (rangeQuery("1Y").from ?? ""))[0];
    expect(readout.getByText(formatDate(earliest.as_of))).toBeInTheDocument();
  });

  it("clears the readout when focus leaves", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("group", { name: /arrow keys/i }));
    expect(screen.getByRole("status", { name: "Chart readout" })).not.toBeEmptyDOMElement();

    await userEvent.tab();

    expect(screen.getByRole("status", { name: "Chart readout" })).toBeEmptyDOMElement();
  });
});

describe("assets and liabilities split", () => {
  it("plots both on one scale, each named and keyed", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("button", { name: "Assets & liabilities" }));

    const summary = within(screen.getByRole("list", { name: "Latest values" }));
    expect(summary.getByText("Assets")).toBeInTheDocument();
    expect(summary.getByText("Liabilities")).toBeInTheDocument();
    expect(summary.getByText(formatCurrency(LATEST.assets_cents))).toBeInTheDocument();
    expect(summary.getByText(formatCurrency(LATEST.liabilities_cents))).toBeInTheDocument();
  });

  it("reads out both series at the focused point", async () => {
    mockNetWorthSeries();

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("button", { name: "Assets & liabilities" }));
    await userEvent.click(screen.getByRole("group", { name: /arrow keys/i }));

    const readout = within(screen.getByRole("status", { name: "Chart readout" }));
    expect(readout.getByText(formatCurrency(LATEST.assets_cents))).toBeInTheDocument();
    expect(readout.getByText(formatCurrency(LATEST.liabilities_cents))).toBeInTheDocument();
    expect(readout.queryByText("Net worth")).not.toBeInTheDocument();
  });

  it("switches without refetching — the split is in the response already", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/net-worth/series", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(netWorthSeries);
      }),
    );

    render(<NetWorthChart view="mine" />);
    await loaded();

    await userEvent.click(screen.getByRole("button", { name: "Assets & liabilities" }));
    const summary = within(screen.getByRole("list", { name: "Latest values" }));
    expect(summary.getByText("Liabilities")).toBeInTheDocument();

    expect(urls).toHaveLength(1);
  });
});

describe("failure", () => {
  it("says the history is unavailable rather than drawing a flat line at zero", async () => {
    server.use(
      http.get("/api/net-worth/series", () =>
        HttpResponse.json({ detail: "not implemented" }, { status: 501 }),
      ),
    );

    render(<NetWorthChart view="mine" />);

    expect(await screen.findByText("Net worth history unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
