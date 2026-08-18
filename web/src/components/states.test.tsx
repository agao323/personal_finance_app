import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmptyState, ErrorBoundary, ErrorState, Skeleton, StaleBadge } from "@/components/states";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Skeleton", () => {
  it("announces itself as loading", () => {
    render(<Skeleton className="h-8 w-32" />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("is announced as an alert", () => {
    render(<ErrorState detail="API unreachable" />);

    expect(screen.getByRole("alert")).toHaveTextContent("API unreachable");
  });

  it("offers retry only when there is something to retry", () => {
    const { rerender } = render(<ErrorState />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    rerender(<ErrorState onRetry={() => {}} />);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("calls onRetry when clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} />);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("EmptyState", () => {
  it("renders its title and optional action", () => {
    render(<EmptyState title="No accounts yet" action={<button>Add one</button>} />);

    expect(screen.getByText("No accounts yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add one" })).toBeInTheDocument();
  });
});

describe("StaleBadge", () => {
  const now = new Date("2026-08-18T00:00:00Z");

  it("says how old the value is, not just that it is old", () => {
    render(<StaleBadge asOf="2026-05-18" now={now} />);

    expect(screen.getByText(/3 months ago/)).toBeInTheDocument();
  });

  it("carries a text label rather than relying on colour", () => {
    // A colourblind reader and a printed page both get nothing from hue alone.
    render(<StaleBadge asOf="2026-05-18" now={now} />);

    expect(screen.getByText(/Updated/)).toBeInTheDocument();
  });

  it("exposes the exact date on hover", () => {
    render(<StaleBadge asOf="2026-05-18" now={now} />);

    expect(screen.getByTitle("Last updated 2026-05-18")).toBeInTheDocument();
  });
});

function Boom(): never {
  throw new Error("tile exploded");
}

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>fine</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("fine")).toBeInTheDocument();
  });

  it("catches a render error instead of blanking the page", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("tile exploded");
  });

  it("renders a custom fallback when given one", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<p>custom fallback</p>}>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByText("custom fallback")).toBeInTheDocument();
  });
});
