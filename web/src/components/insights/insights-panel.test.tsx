import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { InsightsPanel } from "./insights-panel";
import { formatEvidence } from "./finding-row";
import type { ViewScope } from "@/components/view-toggle";
import { actionRoute, SCREENS, screenRoute } from "@/lib/screens";
import { findings, insightsWith, mockFailure, mockInsights } from "@/test/msw";

function Harness() {
  const [view, setView] = useState<ViewScope>("mine");
  return (
    <>
      <button type="button" onClick={() => setView("household")}>
        household
      </button>
      <InsightsPanel view={view} />
    </>
  );
}

describe("insights panel", () => {
  it("keeps the server's order and formats each kind of evidence", async () => {
    mockInsights();

    render(<InsightsPanel view="mine" />);

    const items = await screen.findAllByRole("listitem");
    expect(
      items.map((item) => within(item).getByText(/lapses|days old|went up/).textContent),
    ).toEqual([
      "Dining on Sapphire: $15.00 lapses in 6 days",
      "Brokerage's balance is 120 days old",
      "STREAMLY went up $2.50 per monthly charge",
    ]);
    expect(within(items[0]).getByText("$15.00")).toBeInTheDocument();
    expect(within(items[0]).getByText("Jun 30, 2026")).toBeInTheDocument();
    expect(within(items[1]).getByText("120 days")).toBeInTheDocument();
    expect(within(items[2]).getByText("16.14%")).toBeInTheDocument();
    expect(within(items[2]).getByText("23.4 months")).toBeInTheDocument();
  });

  it("puts each action on its own finding, with the right destination", async () => {
    mockInsights();

    render(<InsightsPanel view="mine" />);

    const items = await screen.findAllByRole("listitem");
    expect(within(items[0]).getByRole("link", { name: "Open card" })).toHaveAttribute(
      "href",
      "/cards/4",
    );
    expect(within(items[1]).getByRole("link", { name: "Update balance" })).toHaveAttribute(
      "href",
      "/accounts/7",
    );
    expect(within(items[1]).getByText("Stale balance")).toBeInTheDocument();
  });

  it("renders a title as text, never as markup", async () => {
    mockInsights([{ ...findings[0], title: '<img src=x onerror="alert(1)">' }]);

    const { container } = render(<InsightsPanel view="mine" />);

    expect(await screen.findByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows five, then expands in place", async () => {
    mockInsights(insightsWith(7));

    render(<InsightsPanel view="mine" />);

    expect(await screen.findAllByRole("listitem")).toHaveLength(5);
    await userEvent.click(screen.getByRole("button", { name: "Show all (7)" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    await userEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("keeps settled findings on screen while the other view loads", async () => {
    const views: (string | null)[] = [];
    mockInsights(findings, (view) => views.push(view));

    render(<Harness />);
    await screen.findAllByRole("listitem");
    await userEvent.click(screen.getByRole("button", { name: "household" }));

    // No skeleton: the findings stay while the household request is in flight.
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    await waitFor(() => expect(views).toEqual(["mine", "household"]));
    await waitFor(() =>
      expect(screen.queryByRole("status", { name: "Refreshing" })).not.toBeInTheDocument(),
    );
  });

  it("says when nothing needs attention", async () => {
    mockInsights([]);

    render(<InsightsPanel view="mine" />);

    expect(await screen.findByText("Nothing needs attention.")).toBeInTheDocument();
  });

  it("shows an error when the first load fails", async () => {
    mockFailure("/api/insights");

    render(<InsightsPanel view="mine" />);

    expect(await screen.findByText("Insights unavailable")).toBeInTheDocument();
  });
});

describe("screens", () => {
  it("maps every screen to an in-app route", () => {
    for (const screenName of SCREENS) {
      expect(screenRoute(screenName)).toMatch(/^\/[a-z/]*$/);
    }
  });

  it("uses an id where the screen takes one", () => {
    expect(actionRoute({ screen: "account", account_id: 3 })).toBe("/accounts/3");
    expect(actionRoute({ screen: "account" })).toBe("/accounts");
    expect(actionRoute({ screen: "rules", account_id: 3 })).toBe("/rules");
  });

  it("formats a missing evidence value as a dash", () => {
    expect(
      formatEvidence({ label: "x", unit: "cents", as_of: "2026-06-25", stale: false, source: "s" }),
    ).toBe("—");
  });
});
