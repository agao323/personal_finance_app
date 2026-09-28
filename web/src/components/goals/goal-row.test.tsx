import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GoalsPage from "@/app/(dashboard)/goals/page";
import PlanningPage from "@/app/(dashboard)/settings/planning/page";
import { NAV_ITEMS } from "@/components/nav";
import { describeTarget, formatMonthsTenths, parseMonthsToTenths } from "@/lib/goals";
import { bpsToInput, parsePercentToBps } from "@/lib/planning";
import {
  accounts,
  categories,
  defaultAssumptions,
  goals,
  mockAccounts,
  mockCategories,
  mockGoals,
  mockPlanning,
} from "@/test/msw";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/goals",
}));

beforeEach(() => {
  localStorage.clear();
  mockCategories(categories);
  mockAccounts();
});

function row(name: string) {
  return screen.getByRole("listitem", { name });
}

describe("the goals screen", () => {
  it("lists each goal with its target and progress, or says progress is not computed", async () => {
    mockGoals();
    render(<GoalsPage />);

    const house = await screen.findByRole("listitem", { name: "House deposit" });
    expect(house).toHaveTextContent("$60,000.00 by Jun 30, 2028, from Savings");
    expect(house).toHaveTextContent("$15,000.00 saved of $60,000.00");
    expect(house).toHaveTextContent("$2,142.86 a month to get there");
    expect(house).toHaveTextContent("Off track");
    expect(within(house).getByText("Stale")).toBeInTheDocument();
    expect(within(house).getByRole("meter", { name: "Progress" })).toHaveAttribute(
      "aria-valuenow",
      "25",
    );

    expect(row("Six months")).toHaveTextContent("6.0 months of spending in cash");
    expect(row("Six months")).toHaveTextContent("Progress not yet computed.");
    expect(within(row("Dining under $400")).getByRole("link")).toHaveAttribute(
      "href",
      "/spending?category=12",
    );
  });

  it("archives a goal from its own row, changing only that row", async () => {
    const calls = mockGoals();
    render(<GoalsPage />);
    const fund = await screen.findByRole("listitem", { name: "Six months" });

    await userEvent.click(within(fund).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(row("Six months")).toHaveTextContent("archived"));
    expect(calls.updated).toEqual([{ id: "2", body: { status: "archived" } }]);
    expect(within(row("Six months")).getByRole("button", { name: "Restore" })).toBeInTheDocument();
    expect(row("House deposit")).not.toHaveTextContent("archived");
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("edits a goal on its row", async () => {
    const calls = mockGoals();
    render(<GoalsPage />);
    const dining = await screen.findByRole("listitem", { name: "Dining under $400" });

    await userEvent.click(within(dining).getByRole("button", { name: "Edit" }));
    const amount = within(dining).getByLabelText("Monthly limit");
    await userEvent.clear(amount);
    await userEvent.type(amount, "350");
    await userEvent.click(within(dining).getByRole("button", { name: "Save goal" }));

    await waitFor(() => expect(calls.updated).toHaveLength(1));
    expect(calls.updated[0].body).toMatchObject({ target_amount_cents: 35_000, category_id: 12 });
  });
});

describe("adding a goal, each kind", () => {
  async function openForm(kind: string) {
    mockGoals([]);
    render(<GoalsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a goal" }));
    const form = screen.getByRole("region", { name: "Add a goal" });
    await userEvent.selectOptions(within(form).getByLabelText("Kind"), kind);
    return form;
  }

  it("a spending limit needs a name, a category and an amount", async () => {
    const form = await openForm("spending_limit");

    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));

    expect(within(form).getByText("Give the goal a name.")).toBeInTheDocument();
    expect(within(form).getByText("Choose a category.")).toBeInTheDocument();
    expect(within(form).getByText("Enter a monthly amount.")).toBeInTheDocument();
  });

  it("adds a spending limit, as a household goal by default", async () => {
    const calls = mockGoals([]);
    render(<GoalsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a goal" }));
    const form = screen.getByRole("region", { name: "Add a goal" });

    await userEvent.type(within(form).getByLabelText("Name"), "Dining");
    await userEvent.selectOptions(within(form).getByLabelText("Category"), "12");
    await userEvent.type(within(form).getByLabelText("Monthly limit"), "400");
    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));

    expect(await screen.findByRole("listitem", { name: "Dining" })).toBeInTheDocument();
    expect(calls.created).toEqual([
      {
        kind: "spending_limit",
        name: "Dining",
        view: "household",
        category_id: 12,
        target_amount_cents: 40_000,
        target_months_tenths: null,
        target_date: null,
        account_ids: [],
      },
    ]);
  });

  it("an emergency fund needs months, and takes a half month", async () => {
    const calls = mockGoals([]);
    render(<GoalsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a goal" }));
    const form = screen.getByRole("region", { name: "Add a goal" });
    await userEvent.selectOptions(within(form).getByLabelText("Kind"), "emergency_fund");
    await userEvent.type(within(form).getByLabelText("Name"), "Cushion");
    await userEvent.type(within(form).getByLabelText("Months of spending"), "six");
    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));
    expect(within(form).getByText(/Enter a number of months/)).toBeInTheDocument();

    const months = within(form).getByLabelText("Months of spending");
    await userEvent.clear(months);
    await userEvent.type(months, "4.5");
    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.created[0]).toMatchObject({ kind: "emergency_fund", target_months_tenths: 45 });
  });

  it("a savings target needs an amount and an account, and can be mine", async () => {
    const calls = mockGoals([]);
    render(<GoalsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a goal" }));
    const form = screen.getByRole("region", { name: "Add a goal" });
    await userEvent.selectOptions(within(form).getByLabelText("Kind"), "savings_target");
    await userEvent.click(within(form).getByRole("button", { name: "Mine" }));
    await userEvent.type(within(form).getByLabelText("Name"), "House");
    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));
    expect(within(form).getByText("Enter the amount to save.")).toBeInTheDocument();
    expect(within(form).getByText(/at least one account/)).toBeInTheDocument();

    await userEvent.type(within(form).getByLabelText("Amount to save"), "60000");
    await userEvent.click(within(form).getByRole("checkbox", { name: "Savings" }));
    await userEvent.click(within(form).getByRole("button", { name: "Add goal" }));

    await waitFor(() => expect(calls.created).toHaveLength(1));
    expect(calls.created[0]).toMatchObject({
      kind: "savings_target",
      view: "mine",
      target_amount_cents: 6_000_000,
      account_ids: [2],
    });
  });

  it("offers only open, non-liability accounts", async () => {
    await openForm("savings_target");

    const liabilityNames = accounts.groups
      .filter((group) => group.kind === "liability")
      .flatMap((group) => group.accounts.map((a) => a.name));
    for (const name of liabilityNames) {
      expect(screen.queryByRole("checkbox", { name })).not.toBeInTheDocument();
    }
  });
});

describe("goal wording", () => {
  it("formats and parses months in tenths without floats", () => {
    expect(formatMonthsTenths(60)).toBe("6.0 months");
    expect(formatMonthsTenths(45)).toBe("4.5 months");
    expect(parseMonthsToTenths("6")).toBe(60);
    expect(parseMonthsToTenths("4.5")).toBe(45);
    expect(parseMonthsToTenths("4.55")).toBeNull();
    expect(parseMonthsToTenths("six")).toBeNull();
  });

  it("describes each kind's target in one line", () => {
    expect(describeTarget(goals[2])).toBe("$400.00 a month on Restaurants");
    expect(describeTarget(goals[1])).toBe("6.0 months of spending in cash");
    expect(describeTarget(goals[0], new Map([[2, "Savings"]]))).toBe(
      "$60,000.00 by Jun 30, 2028, from Savings",
    );
  });

  it("puts Goals in the nav after Spending", () => {
    const labels = NAV_ITEMS.map((item) => item.label);
    expect(labels.indexOf("Goals")).toBe(labels.indexOf("Spending") + 1);
  });
});

describe("planning", () => {
  it("shows the defaults as defaults, and appends a version when they change", async () => {
    const calls = mockPlanning();
    render(<PlanningPage />);
    const assumptions = await screen.findByRole("region", { name: "Assumptions" });
    expect(within(assumptions).getByText("Defaults")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Earlier versions" })).not.toBeInTheDocument();

    await userEvent.click(within(assumptions).getByRole("button", { name: "Change" }));
    const inflation = within(assumptions).getByLabelText("Inflation (%)");
    await userEvent.clear(inflation);
    await userEvent.type(inflation, "3.25");
    await userEvent.click(
      within(assumptions).getByRole("button", { name: "Save as a new version" }),
    );

    await waitFor(() => expect(calls.versions).toHaveLength(1));
    expect(calls.versions[0]).toMatchObject({ inflation_bps: 325, target_us_equity_bps: 4000 });
    const earlier = await screen.findByRole("region", { name: "Earlier versions" });
    expect(within(earlier).getAllByRole("listitem")).toHaveLength(1);
    expect(within(earlier).getByText(/defaults/)).toBeInTheDocument();
    expect(within(assumptions).queryByText("Defaults")).not.toBeInTheDocument();
  });

  it("will not save a mix that does not total 100%", async () => {
    const calls = mockPlanning();
    render(<PlanningPage />);
    const assumptions = await screen.findByRole("region", { name: "Assumptions" });
    await userEvent.click(within(assumptions).getByRole("button", { name: "Change" }));
    expect(within(assumptions).getByText("Total: 100%")).toBeInTheDocument();

    const bonds = within(assumptions).getByLabelText("Bonds");
    await userEvent.clear(bonds);
    await userEvent.type(bonds, "30");
    expect(within(assumptions).getByText("Total: 95% — it must total 100%")).toBeInTheDocument();
    await userEvent.click(
      within(assumptions).getByRole("button", { name: "Save as a new version" }),
    );

    expect(within(assumptions).getByRole("alert")).toHaveTextContent("must total 100%");
    expect(calls.versions).toEqual([]);
  });

  it("saves your profile years", async () => {
    const calls = mockPlanning([{ ...defaultAssumptions }]);
    render(<PlanningPage />);
    const profile = await screen.findByRole("region", { name: "Your profile" });

    await userEvent.type(within(profile).getByLabelText("Birth year"), "1988");
    await userEvent.type(within(profile).getByLabelText("Target retirement year"), "2048");
    await userEvent.click(within(profile).getByRole("button", { name: "Save profile" }));

    await waitFor(() =>
      expect(calls.profiles).toEqual([{ birth_year: 1988, target_retirement_year: 2048 }]),
    );
  });

  it("converts percentages and basis points exactly", () => {
    expect(parsePercentToBps("5")).toBe(500);
    expect(parsePercentToBps("3.25")).toBe(325);
    expect(parsePercentToBps("4.5")).toBe(450);
    expect(parsePercentToBps("-1.5")).toBe(-150);
    expect(parsePercentToBps("4.555")).toBeNull();
    expect(bpsToInput(500)).toBe("5");
    expect(bpsToInput(325)).toBe("3.25");
    expect(bpsToInput(450)).toBe("4.5");
    expect(bpsToInput(-150)).toBe("-1.5");
  });
});
