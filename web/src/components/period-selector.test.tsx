import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  PeriodSelector,
  presetPeriod,
  priorPeriodLabel,
  type Period,
} from "@/components/period-selector";

// A fixed "today" in the middle of a month and a year, so both presets have a
// visible span rather than collapsing to a single day.
const TODAY = new Date("2026-08-18T00:00:00Z");

describe("presetPeriod", () => {
  it("runs month to date from the first of the month", () => {
    expect(presetPeriod("MTD", TODAY)).toEqual({
      key: "MTD",
      from: "2026-08-01",
      to: "2026-08-18",
    });
  });

  it("runs year to date from the first of January", () => {
    expect(presetPeriod("YTD", TODAY)).toEqual({
      key: "YTD",
      from: "2026-01-01",
      to: "2026-08-18",
    });
  });

  it("uses UTC, so the boundary does not shift for a reader west of Greenwich", () => {
    // 22:00 on 31 July in New York is already 1 August UTC. Local-time arithmetic
    // would call this July and report a month of spending that has ended.
    const lateJuly = new Date("2026-08-01T02:00:00Z");

    expect(presetPeriod("MTD", lateJuly).from).toBe("2026-08-01");
  });

  it("handles the first of the month, where the period is one day", () => {
    const first = new Date("2026-08-01T00:00:00Z");

    expect(presetPeriod("MTD", first)).toEqual({
      key: "MTD",
      from: "2026-08-01",
      to: "2026-08-01",
    });
  });
});

describe("priorPeriodLabel", () => {
  it("counts both ends, because the API's range is inclusive", () => {
    // 1 to 18 August is 18 days, not 17: the API compares against the 18 days before
    // it, and an off-by-one here would describe the wrong window.
    expect(priorPeriodLabel({ key: "MTD", from: "2026-08-01", to: "2026-08-18" })).toBe(
      "the previous 18 days",
    );
  });

  it("says day, singular, for a one-day period", () => {
    expect(priorPeriodLabel({ key: "MTD", from: "2026-08-01", to: "2026-08-01" })).toBe(
      "the previous day",
    );
  });
});

describe("PeriodSelector", () => {
  it("marks the active preset as pressed", () => {
    render(<PeriodSelector period={presetPeriod("YTD", TODAY)} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "This year" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "This month" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("hides the date fields until a custom range is chosen", async () => {
    const onChange = vi.fn();
    render(<PeriodSelector period={presetPeriod("MTD", TODAY)} onChange={onChange} />);

    expect(screen.queryByLabelText("From")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Custom" }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ key: "CUSTOM", from: "2026-08-01", to: "2026-08-18" }),
    );
  });

  it("keeps the current bounds when switching to custom, so the numbers do not move", async () => {
    const onChange = vi.fn();
    render(<PeriodSelector period={presetPeriod("YTD", TODAY)} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Custom" }));

    // The window that was on screen, now editable — not a reset to some default.
    expect(onChange).toHaveBeenCalledWith({ key: "CUSTOM", from: "2026-01-01", to: "2026-08-18" });
  });

  it("reports an edited start date", () => {
    const onChange = vi.fn();
    const custom: Period = { key: "CUSTOM", from: "2026-08-01", to: "2026-08-18" };
    render(<PeriodSelector period={custom} onChange={onChange} />);

    // `fireEvent.change` rather than `userEvent.type`: the input is controlled by the
    // `period` prop, and typing a date segment at a time against a parent that never
    // updates it just re-renders the old value after every keystroke.
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-07-04" } });

    expect(onChange).toHaveBeenLastCalledWith({
      key: "CUSTOM",
      from: "2026-07-04",
      to: "2026-08-18",
    });
  });

  it("ignores a cleared date rather than sending an empty bound", () => {
    const onChange = vi.fn();
    const custom: Period = { key: "CUSTOM", from: "2026-08-01", to: "2026-08-18" };
    render(<PeriodSelector period={custom} onChange={onChange} />);

    // A half-typed date momentarily reads as "". Passing that through would send
    // `from=` to the API, which would have to guess what an empty bound means.
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "" } });

    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ from: "2026-08-01" }));
  });

  it("stops the two date fields from crossing", () => {
    const custom: Period = { key: "CUSTOM", from: "2026-03-01", to: "2026-06-30" };
    render(<PeriodSelector period={custom} onChange={() => {}} />);

    // A reversed range is not an error worth a message — the control refuses it.
    expect(screen.getByLabelText("From")).toHaveAttribute("max", "2026-06-30");
    expect(screen.getByLabelText("to")).toHaveAttribute("min", "2026-03-01");
  });
});
