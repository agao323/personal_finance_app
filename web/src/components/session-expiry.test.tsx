import { render, screen } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it } from "vitest";

import { SessionExpiry } from "@/components/session-expiry";
import { SESSION_EXPIRED_EVENT } from "@/lib/api";

describe("SessionExpiry", () => {
  it("shows nothing until a session actually expires", () => {
    const { container } = render(<SessionExpiry />);

    expect(container).toBeEmptyDOMElement();
  });

  it("explains what happened rather than showing an error panel", () => {
    // Nothing is broken — the session ended. "Could not load this" would send the
    // reader debugging their network.
    render(<SessionExpiry />);

    act(() => {
      globalThis.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Your session ended");
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("sends the reader back where they were", () => {
    render(<SessionExpiry />);

    act(() => {
      globalThis.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });

    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      expect.stringContaining("next="),
    );
  });
});
