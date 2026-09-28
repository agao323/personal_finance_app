import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AllocationPanel, percentBps, readPercents } from "./allocation-panel";
import { TermsPanel, formatApr, parseApr, termsBody } from "./terms-panel";
import { allocation, liabilityTerms, mockAllocations, mockTerms } from "@/test/msw";

const TODAY = "2026-08-18";

describe("allocation arithmetic", () => {
  it("reads percents to the basis point", () => {
    expect(percentBps("39.99")).toBe(3999);
    expect(percentBps("12.5")).toBe(1250);
    expect(percentBps("40%")).toBe(4000);
    expect(percentBps("forty")).toBeNull();
    expect(percentBps("1.234")).toBeNull();
  });

  it("refuses a total of 99.99%, and leaves out blank and zero classes", () => {
    const blank = {
      us_equity: "",
      intl_equity: "",
      bonds: "",
      cash: "",
      real_estate: "",
      other: "",
    };

    expect(readPercents({ ...blank, us_equity: "60", bonds: "39.99" }).problem).toMatch(
      /total 99\.99%/,
    );
    expect(readPercents({ ...blank, us_equity: "100", bonds: "0" })).toEqual({
      shares: [{ asset_class: "us_equity", percentage_bps: 10_000 }],
      totalBps: 10_000,
      problem: null,
    });
  });
});

describe("AllocationPanel", () => {
  it("shows the current percentages and the history of changes", async () => {
    mockAllocations();

    render(<AllocationPanel accountId={3} today={TODAY} />);

    const panel = await screen.findByRole("region", { name: "Allocation" });
    expect(await within(panel).findByText("US stocks")).toBeInTheDocument();
    expect(within(panel).getByText("60%")).toBeInTheDocument();
    expect(
      within(panel).getByText("US stocks 60%, Bonds 40%", { exact: false }),
    ).toBeInTheDocument();
    // Half-open ranges: the cash allocation's last day was the day before January 1.
    expect(within(panel).getByText("Mar 1, 2025 — Dec 31, 2025")).toBeInTheDocument();
    expect(within(panel).getByText("Jan 1, 2026 — now")).toBeInTheDocument();
  });

  it("says unknown when nothing is recorded, rather than guessing", async () => {
    mockAllocations({ status: "unknown", shares: [], history: [] });

    render(<AllocationPanel accountId={3} today={TODAY} />);

    expect(await screen.findByText(/^Unknown\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set allocation" })).toBeInTheDocument();
  });

  it("fills the form from a preset", async () => {
    const user = userEvent.setup();
    mockAllocations({ status: "unknown", shares: [], history: [] });
    render(<AllocationPanel accountId={3} today={TODAY} />);

    await user.click(await screen.findByRole("button", { name: "Set allocation" }));
    await user.click(screen.getByRole("button", { name: "Target-date 2055 ≈ 90/10" }));

    expect(screen.getByLabelText("US stocks")).toHaveValue("54");
    expect(screen.getByLabelText("International stocks")).toHaveValue("36");
    expect(screen.getByLabelText("Bonds")).toHaveValue("10");
    expect(screen.getByLabelText("Cash")).toHaveValue("");
    expect(screen.getByText("Total 100%")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "100% cash" }));

    expect(screen.getByLabelText("Cash")).toHaveValue("100");
    expect(screen.getByLabelText("US stocks")).toHaveValue("");
  });

  it("will not save a total of 99.99%", async () => {
    const user = userEvent.setup();
    const { posts } = mockAllocations();
    render(<AllocationPanel accountId={3} today={TODAY} />);

    await user.click(await screen.findByRole("button", { name: "Change allocation" }));
    const bonds = screen.getByLabelText("Bonds");
    await user.clear(bonds);
    await user.type(bonds, "39.99");

    expect(screen.getByText(/total 99\.99%; they must total 100%/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save allocation" });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(posts).toHaveLength(0);
  });

  it("saves a new allocation from a date and shows the server's answer in place", async () => {
    const user = userEvent.setup();
    const { posts } = mockAllocations();
    render(<AllocationPanel accountId={3} today={TODAY} />);

    await user.click(await screen.findByRole("button", { name: "Change allocation" }));
    await user.click(screen.getByRole("button", { name: "Target-date 2055 ≈ 90/10" }));
    await user.click(screen.getByRole("button", { name: "Save allocation" }));

    expect(await screen.findByRole("button", { name: "Change allocation" })).toBeInTheDocument();
    expect(posts).toEqual([
      {
        effective_from: TODAY,
        shares: [
          { asset_class: "us_equity", percentage_bps: 5400 },
          { asset_class: "intl_equity", percentage_bps: 3600 },
          { asset_class: "bonds", percentage_bps: 1000 },
        ],
      },
    ]);
    expect(screen.getByText("Aug 18, 2026 — now")).toBeInTheDocument();
    expect(screen.getByText("Jan 1, 2026 — Aug 17, 2026")).toBeInTheDocument();
  });

  it("is absent for a debt", async () => {
    mockAllocations({ status: "not_applicable", shares: [], history: [] });

    const { container } = render(<AllocationPanel accountId={3} today={TODAY} />);

    await expect.poll(() => container.textContent).toBe("");
  });

  it("keeps the fixture's shares summing to 100%", () => {
    expect(allocation.shares.reduce((sum, share) => sum + share.percentage_bps, 0)).toBe(10_000);
  });
});

describe("terms arithmetic", () => {
  it("formats and reads an APR to three decimals", () => {
    expect(formatApr(6875)).toBe("6.875%");
    expect(formatApr(24_990)).toBe("24.990%");
    expect(formatApr(0)).toBe("0.000%");
    expect(parseApr("6.875")).toBe(6875);
    expect(parseApr("7")).toBe(7000);
    expect(parseApr("6.8755")).toBeNull();
    expect(parseApr("101")).toBeNull();
  });

  it("needs a promotion's end date", () => {
    const values = {
      apr: "24.99",
      minimumPayment: "",
      creditLimit: "",
      termMonths: "",
      maturityOn: "",
      promoApr: "0",
      promoEndsOn: "",
      asOf: TODAY,
    };

    const outcome = termsBody(values, { minimumPayment: null, creditLimit: null });

    expect(outcome).toEqual({
      errors: { promoEndsOn: "A promotional rate needs the date it ends." },
    });
  });
});

describe("TermsPanel", () => {
  it("shows the terms and when they were checked", async () => {
    mockTerms();

    render(<TermsPanel accountId={3} isCard today={TODAY} />);

    const panel = await screen.findByRole("region", { name: "Terms" });
    expect(await within(panel).findByText("24.990%")).toBeInTheDocument();
    expect(within(panel).getByText("$5,000.00")).toBeInTheDocument();
    expect(within(panel).getByText(/Checked on Aug 1, 2026/)).toBeInTheDocument();
    expect(within(panel).queryByText(/More than a year old/)).not.toBeInTheDocument();
  });

  it("marks terms checked more than a year ago as stale", async () => {
    mockTerms({ ...liabilityTerms, as_of: "2025-06-01", stale: true });

    render(<TermsPanel accountId={3} isCard today={TODAY} />);

    expect(await screen.findByText(/More than a year old/)).toBeInTheDocument();
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
  });

  it("invites terms when none are recorded", async () => {
    mockTerms(null);

    render(<TermsPanel accountId={3} isCard={false} today={TODAY} />);

    expect(await screen.findByText(/No terms recorded/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record terms" })).toBeInTheDocument();
  });

  it("saves terms and checks them as of today", async () => {
    const user = userEvent.setup();
    const { puts } = mockTerms({ ...liabilityTerms, as_of: "2025-06-01", stale: true });
    render(<TermsPanel accountId={3} isCard today={TODAY} />);

    await user.click(await screen.findByRole("button", { name: "Update terms" }));
    const apr = screen.getByLabelText("APR");
    await user.clear(apr);
    await user.type(apr, "22.49");
    await user.click(screen.getByRole("button", { name: "Save terms" }));

    expect(await screen.findByText("22.490%")).toBeInTheDocument();
    expect(screen.queryByText(/More than a year old/)).not.toBeInTheDocument();
    expect(puts).toEqual([
      expect.objectContaining({
        apr_pct_thousandths: 22_490,
        minimum_payment_cents: 3_500,
        credit_limit_cents: 500_000,
        as_of: TODAY,
      }),
    ]);
  });
});
