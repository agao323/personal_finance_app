import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import DashboardPage from "./page";
import { mockFailure, mockNetWorth, mockNetWorthSeries, mockRunway } from "@/test/msw";

beforeEach(() => {
  globalThis.localStorage.clear();
  // The dashboard carries the net worth chart (027), which fetches on mount. MSW is
  // configured to error on an unhandled request, so it needs a handler in every test
  // here — but none of them assert on it, so it lives in the setup rather than
  // repeated in each case.
  mockNetWorthSeries();
});

describe("dashboard", () => {
  it("shows skeletons before the data arrives, not a blank panel", () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);

    expect(screen.getAllByRole("status", { name: "Loading" }).length).toBeGreaterThan(0);
  });

  it("renders net worth with assets and liabilities", async () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);

    expect(await screen.findByText("$123,456.78")).toBeInTheDocument();
    expect(screen.getByText("$150,000.00")).toBeInTheDocument();
    expect(screen.getByText("$26,543.22")).toBeInTheDocument();
  });

  it("renders the delta against the prior month", async () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);

    // 12,345,678 vs 11,000,000 cents.
    expect(await screen.findByText("+$13,456.78")).toBeInTheDocument();
    expect(screen.getByText("(+12.2%)")).toBeInTheDocument();
    expect(screen.getByText("vs last month")).toBeInTheDocument();
  });

  it("renders runway with its definition on the tile", async () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);

    expect(await screen.findByText("10.0 months")).toBeInTheDocument();
    // A runway number whose definition is ambiguous is worse than none.
    expect(screen.getByText(/gross spend/)).toBeInTheDocument();
    expect(screen.getByText(/transfers excluded/)).toBeInTheDocument();
  });

  it("says the partial month was excluded when it was", async () => {
    mockNetWorth();
    mockRunway({ partial_month_excluded: true });

    render(<DashboardPage />);

    expect(await screen.findByText(/partial month excluded/i)).toBeInTheDocument();
  });

  it("survives an empty history without a prior period", async () => {
    mockNetWorth({}, null);
    mockRunway();

    render(<DashboardPage />);

    expect(await screen.findByText("$123,456.78")).toBeInTheDocument();
    // No prior period is not an error, and no percentage is invented for it.
    expect(screen.queryByText(/vs last month/)).not.toBeInTheDocument();
  });

  it("shows an empty runway message when there is not enough history", async () => {
    mockNetWorth();
    mockRunway({ windows: [] });

    render(<DashboardPage />);

    expect(await screen.findByText("Not enough history")).toBeInTheDocument();
  });

  it("shows an error on one tile without blanking the other", async () => {
    mockNetWorth();
    mockFailure("/api/runway");

    render(<DashboardPage />);

    expect(await screen.findByText("Runway unavailable")).toBeInTheDocument();
    expect(screen.getByText("$123,456.78")).toBeInTheDocument();
  });

  it("flags a stale balance rather than silently trusting it", async () => {
    mockNetWorth({ stale_account_ids: [3, 7] });
    mockRunway();

    render(<DashboardPage />);

    expect(
      await screen.findByText(/2 accounts using a balance over 90 days old/),
    ).toBeInTheDocument();
  });
});

describe("mine / household toggle", () => {
  it("defaults to mine", async () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);

    expect(await screen.findByRole("button", { name: "Mine" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("refetches against the household scope when switched", async () => {
    mockNetWorth();
    mockRunway();

    render(<DashboardPage />);
    await screen.findByText("$123,456.78");

    await userEvent.click(screen.getByRole("button", { name: "Household" }));

    expect(await screen.findByText("Household net worth")).toBeInTheDocument();
  });

  it("persists the choice across navigation", async () => {
    mockNetWorth();
    mockRunway();

    const { unmount } = render(<DashboardPage />);
    await screen.findByText("$123,456.78");
    await userEvent.click(screen.getByRole("button", { name: "Household" }));

    await waitFor(() =>
      expect(globalThis.localStorage.getItem("pfa:view-scope")).toBe("household"),
    );
    unmount();

    mockNetWorth();
    mockRunway();
    render(<DashboardPage />);

    expect(await screen.findByRole("button", { name: "Household" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
