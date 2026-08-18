import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NAV_ITEMS, Nav, isActive } from "@/components/nav";

const pathname = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

beforeEach(() => {
  pathname.current = "/";
});

describe("isActive", () => {
  it("matches the dashboard only at the root", () => {
    // Without the special case, "/" prefix-matches every route and every tab
    // lights up at once.
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/accounts", "/")).toBe(false);
  });

  it("matches a section exactly", () => {
    expect(isActive("/accounts", "/accounts")).toBe(true);
  });

  it("matches a child route to its section", () => {
    expect(isActive("/accounts/7", "/accounts")).toBe(true);
    expect(isActive("/accounts/7/history", "/accounts")).toBe(true);
  });

  it("does not match a route that merely shares a prefix", () => {
    expect(isActive("/accounts-archive", "/accounts")).toBe(false);
  });
});

describe("Nav", () => {
  it("renders every destination", () => {
    render(<Nav />);

    for (const item of NAV_ITEMS) {
      expect(screen.getByRole("link", { name: item.label })).toBeInTheDocument();
    }
  });

  it("marks exactly one item as the current page", () => {
    pathname.current = "/accounts/7";
    render(<Nav />);

    const current = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current"));

    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Accounts");
  });

  it("marks the dashboard current at the root", () => {
    render(<Nav />);

    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });
});
