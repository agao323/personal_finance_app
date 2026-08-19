import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline, sparkGeometry } from "@/components/charts/sparkline";

describe("sparkGeometry", () => {
  it("spreads points evenly and inverts the y axis", () => {
    const { xs, ys } = sparkGeometry([
      { as_of: "2026-01-01", balance_cents: 100 },
      { as_of: "2026-02-01", balance_cents: 200 },
      { as_of: "2026-03-01", balance_cents: 300 },
    ]);

    expect(xs[0]).toBeLessThan(xs[1]);
    expect(xs[1]).toBeLessThan(xs[2]);
    // Larger balance, smaller y — SVG's origin is top-left.
    expect(ys[2]).toBeLessThan(ys[0]);
  });

  it("centres a flat history rather than dividing by a zero range", () => {
    // A NaN in a path string renders as nothing at all: a silently blank chart
    // rather than a loud failure, which is the worst way for this to break.
    const { ys } = sparkGeometry([
      { as_of: "2026-01-01", balance_cents: 500 },
      { as_of: "2026-02-01", balance_cents: 500 },
    ]);

    expect(ys.every(Number.isFinite)).toBe(true);
    expect(ys[0]).toBe(ys[1]);
  });

  it("centres a single point instead of pinning it to the left edge", () => {
    const { xs } = sparkGeometry([{ as_of: "2026-01-01", balance_cents: 500 }]);

    expect(xs[0]).toBeGreaterThan(0);
    expect(Number.isFinite(xs[0])).toBe(true);
  });
});

describe("Sparkline", () => {
  it("renders nothing at all for an empty history", () => {
    const { container } = render(<Sparkline points={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("draws no line for one point, but still marks it", () => {
    const { container } = render(
      <Sparkline points={[{ as_of: "2026-01-01", balance_cents: 500 }]} />,
    );

    expect(container.querySelector("path")).toBeNull();
    expect(container.querySelector("circle")).not.toBeNull();
  });

  it("never emits NaN into the path", () => {
    const { container } = render(
      <Sparkline
        points={[
          { as_of: "2026-01-01", balance_cents: 500 },
          { as_of: "2026-02-01", balance_cents: 500 },
        ]}
      />,
    );

    expect(container.querySelector("path")?.getAttribute("d")).not.toContain("NaN");
  });

  it("is hidden from assistive technology, because the caller tables the data", () => {
    const { container } = render(
      <Sparkline
        points={[
          { as_of: "2026-01-01", balance_cents: 100 },
          { as_of: "2026-02-01", balance_cents: 200 },
        ]}
      />,
    );

    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
