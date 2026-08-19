import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RulesScreen } from "./page";
import { inRunOrder, swapTarget } from "@/components/rules/rule-list";
import { draftFrom, validateRule } from "@/components/rules/rule-form";
import { mockCategories, mockRules, rules, server } from "@/test/msw";

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams.current }));

beforeEach(() => {
  searchParams.current = new URLSearchParams();
  mockRules();
  mockCategories();
});

function listOrder() {
  return within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

// ── pure ────────────────────────────────────────────────────────────────────────

describe("inRunOrder", () => {
  it("orders by priority then id, matching the engine", () => {
    const shuffled = [
      { ...rules[1], id: 5, priority: 100 },
      { ...rules[0], id: 3, priority: 100 },
      { ...rules[0], id: 1, priority: 50 },
    ];

    expect(inRunOrder(shuffled).map((rule) => rule.id)).toEqual([1, 3, 5]);
  });
});

describe("swapTarget", () => {
  it("pairs a rule with the one above it", () => {
    const target = swapTarget(rules, 2, "up")!;

    expect([target.rule.id, target.other.id]).toEqual([2, 1]);
  });

  it("returns nothing at the ends, so the button can be absent rather than inert", () => {
    expect(swapTarget(rules, 1, "up")).toBeNull();
    expect(swapTarget(rules, 2, "down")).toBeNull();
  });
});

describe("validateRule", () => {
  it("requires a pattern and a category", () => {
    const errors = validateRule(draftFrom(null));

    expect(errors.pattern).toBeTruthy();
    expect(errors.categoryId).toBeTruthy();
  });

  it("accepts a complete draft", () => {
    expect(validateRule({ pattern: "AMZN", matchType: "contains", categoryId: 11 })).toEqual({});
  });
});

// ── the screen ──────────────────────────────────────────────────────────────────

describe("rules screen", () => {
  it("lists rules in run order and numbers them", async () => {
    render(<RulesScreen />);

    await screen.findByText("CORNER MARKET");
    expect(listOrder()[0]).toContain("CORNER MARKET");
    expect(listOrder()[1]).toContain("AMZN");
  });

  it("states that manual categorisations survive", async () => {
    // The property that makes anyone willing to press "run all rules". It is
    // permanent text, not a toast that appears after the fact.
    render(<RulesScreen />);

    expect(await screen.findByText(/categorised by hand is never overwritten/)).toBeInTheDocument();
  });

  it("reorders a rule and keeps the new order", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");

    await userEvent.click(screen.getByRole("button", { name: "Move ^AMZN earlier" }));

    await waitFor(() => expect(listOrder()[0]).toContain("AMZN"));
  });

  it("cannot move the first rule up", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");

    expect(screen.getByRole("button", { name: "Move CORNER MARKET earlier" })).toBeDisabled();
  });

  it("deletes a rule", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");

    await userEvent.click(screen.getByRole("button", { name: "Delete CORNER MARKET" }));

    await waitFor(() => expect(screen.queryByText("CORNER MARKET")).not.toBeInTheDocument());
  });

  it("summarises a run, including what it left alone", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");

    await userEvent.click(screen.getByRole("button", { name: "Run all rules" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Examined 120 transactions and changed 8");
    expect(status).toHaveTextContent("3 were left alone");
  });

  // ── the match preview ─────────────────────────────────────────────────────────

  it("shows which existing transactions a pattern would hit", async () => {
    // Writing a pattern against your own history without seeing what it matches is
    // how two years of data get re-categorised unnoticed.
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "Corner");
    await userEvent.click(screen.getByRole("button", { name: "Check what this matches" }));

    expect(await screen.findByText(/Matches 2 transactions/)).toBeInTheDocument();
  });

  it("says how many matches it would leave alone", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "Corner");
    await userEvent.click(screen.getByRole("button", { name: "Check what this matches" }));

    expect(await screen.findByText(/1 of them you categorised by hand/)).toBeInTheDocument();
  });

  it("says a pattern matches nothing rather than showing an empty table", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "zzz");
    await userEvent.click(screen.getByRole("button", { name: "Check what this matches" }));

    expect(await screen.findByText("Matches nothing yet")).toBeInTheDocument();
    expect(screen.getByText(/still apply to anything imported later/)).toBeInTheDocument();
  });

  it("surfaces a rejected pattern at preview time, not at save time", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "(a+)+b");
    await userEvent.click(screen.getByRole("button", { name: "Check what this matches" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("backtracks exponentially");
  });

  it("drops a stale preview when the pattern changes", async () => {
    // A preview of the previous pattern beside a changed one reads as confirmation
    // of what is now on screen.
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "Corner");
    await userEvent.click(screen.getByRole("button", { name: "Check what this matches" }));
    await screen.findByText(/Matches 2 transactions/);

    await userEvent.type(screen.getByLabelText("When the merchant"), "X");

    expect(screen.queryByText(/Matches 2 transactions/)).not.toBeInTheDocument();
  });

  // ── prefill ───────────────────────────────────────────────────────────────────

  it("opens the form prefilled when linked to with a merchant", async () => {
    // The loop: spending shows uncategorised → this arrives already filled in.
    searchParams.current = new URLSearchParams("pattern=SQ *UNKNOWN");

    render(<RulesScreen />);

    expect(await screen.findByLabelText("When the merchant")).toHaveValue("SQ *UNKNOWN");
  });

  it("creates a rule and shows it in the list", async () => {
    render(<RulesScreen />);
    await screen.findByText("CORNER MARKET");
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));

    await userEvent.type(screen.getByLabelText("When the merchant"), "TESCO");
    await userEvent.selectOptions(screen.getByLabelText("Categorise it as"), "11");
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));

    expect(await screen.findByText("TESCO")).toBeInTheDocument();
  });

  it("says rules are unavailable rather than showing an empty set", async () => {
    server.use(http.get("/api/rules", () => HttpResponse.json({ detail: "no" }, { status: 500 })));

    render(<RulesScreen />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Rules problem");
  });
});
