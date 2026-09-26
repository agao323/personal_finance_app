import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NetValue } from "@/components/cards/net-value";
import { cards } from "@/test/msw";

describe("NetValue", () => {
  it("shows the fee, what was realised, and the gap", () => {
    render(<NetValue card={cards[0]} />);

    expect(screen.getByText("$695.00")).toBeInTheDocument();
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    // 695 − 25: behind, and shown as a deficit rather than a negative-looking total.
    expect(screen.getByText("−$670.00")).toBeInTheDocument();
  });

  it("renders nothing when no fee is recorded", () => {
    // Absent is not zero. A card with no fee must not claim its fee is $0.
    const { container } = render(
      <NetValue
        card={{ ...cards[0], annual_fee_cents: null, realised_this_fee_year_cents: null }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("says the figure counts what was used, not what was available", () => {
    // The distinction that stops the number flattering every card.
    render(<NetValue card={cards[0]} />);

    expect(screen.getByText(/not what was available/)).toBeInTheDocument();
  });
});
