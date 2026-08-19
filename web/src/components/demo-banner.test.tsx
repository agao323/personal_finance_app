import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/demo-banner";

describe("DemoBanner", () => {
  it("renders nothing outside the demo build", () => {
    // IS_DEMO is inlined at build time, so the real bundle does not contain this
    // markup at all — this asserts the behaviour the inlining produces.
    const { container } = render(<DemoBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("says the data is generated when the demo flag is on", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO", "true");
    vi.resetModules();
    const { DemoBanner: Banner } = await import("@/components/demo-banner");

    render(<Banner />);

    expect(screen.getByText(/Every figure here is generated/)).toBeInTheDocument();
    expect(screen.getByText(/Editing is disabled/)).toBeInTheDocument();

    vi.unstubAllEnvs();
    vi.resetModules();
  });
});
