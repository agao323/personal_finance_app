import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdvisorScreen } from "@/app/(dashboard)/advisor/page";
import { NAV_ITEMS, Nav } from "@/components/nav";
import { REASONS, takeQuestion } from "@/lib/advisor";
import { mockAdvisor, mockFailure } from "@/test/msw";

const push = vi.fn();
const pathname = vi.hoisted(() => ({ current: "/advisor" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => pathname.current,
}));

beforeEach(() => {
  push.mockReset();
  localStorage.clear();
  sessionStorage.clear();
});

describe("the advisor screen", () => {
  it("lists your conversations, newest first, with their view", async () => {
    mockAdvisor();

    render(<AdvisorScreen />);

    const rows = within(await screen.findByRole("list", { name: "Conversations" })).getAllByRole(
      "listitem",
    );
    expect(rows.map((row) => within(row).getByRole("link").textContent)).toEqual([
      expect.stringContaining("What did we spend on dining?"),
      expect.stringContaining("What's my net worth?"),
    ]);
    expect(rows[0]).toHaveTextContent("Household · 3 questions");
    expect(rows[1]).toHaveTextContent("Mine · 1 question");
    expect(within(rows[0]).getByRole("link")).toHaveAttribute(
      "href",
      "/advisor/7d0c9f5e-0000-4000-8000-000000000002",
    );
  });

  it.each(["mine", "household"] as const)(
    "starts a conversation in the %s view and carries the question without the URL",
    async (view) => {
      const calls = mockAdvisor();
      render(<AdvisorScreen />);
      await screen.findByRole("list", { name: "Conversations" });
      if (view === "household") {
        await userEvent.click(screen.getByRole("button", { name: "Household" }));
      }

      await userEvent.type(screen.getByLabelText("Ask about your money"), "Net worth?");
      await userEvent.click(screen.getByRole("button", { name: "Ask" }));

      await waitFor(() => expect(push).toHaveBeenCalled());
      expect(calls.created).toEqual([{ view, kind: "chat" }]);
      const target = push.mock.calls[0][0] as string;
      expect(target).toBe("/advisor/7d0c9f5e-0000-4000-8000-0000000000ff");
      expect(target).not.toContain("Net");
      expect(takeQuestion("7d0c9f5e-0000-4000-8000-0000000000ff")).toBe("Net worth?");
    },
  );

  it("says when it is ready, and what this month has cost", async () => {
    mockAdvisor();

    render(<AdvisorScreen />);

    expect(await screen.findByText("Ready. This month: $3.12 of $20.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask about your money")).toBeEnabled();
  });

  it.each([
    ["disabled", REASONS.disabled],
    ["demo", REASONS.demo],
    ["not_configured", REASONS.not_configured],
    ["monthly_cap", `${REASONS.monthly_cap} It resets on Oct 1, 2026.`],
  ] as const)(
    "explains %s, disables the question box and points to Insights",
    async (reason, text) => {
      mockAdvisor({ status: { enabled: false, reason } });

      render(<AdvisorScreen />);

      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(screen.getByLabelText("Ask about your money")).toBeDisabled();
      expect(screen.getByRole("link", { name: "Insights on the dashboard" })).toHaveAttribute(
        "href",
        "/",
      );
    },
  );

  it("deletes one conversation in place, from its own row", async () => {
    const calls = mockAdvisor();
    render(<AdvisorScreen />);
    const list = await screen.findByRole("list", { name: "Conversations" });

    await userEvent.click(
      within(list).getByRole("button", { name: "Delete “What did we spend on dining?”" }),
    );
    const dialog = screen.getByRole("alertdialog", { name: "Delete this conversation" });
    expect(dialog).toHaveTextContent("gone from the app now");
    expect(dialog).toHaveTextContent("backup files already written remain");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(1));
    expect(calls.deleted).toEqual(["7d0c9f5e-0000-4000-8000-000000000002"]);
    expect(within(list).getByText("What's my net worth?")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading" })).not.toBeInTheDocument();
  });

  it("keeps a conversation when the delete is cancelled", async () => {
    const calls = mockAdvisor();
    render(<AdvisorScreen />);
    const list = await screen.findByRole("list", { name: "Conversations" });

    await userEvent.click(
      within(list).getByRole("button", { name: "Delete “What's my net worth?”" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));

    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(calls.deleted).toEqual([]);
  });

  it("shows the count only near the limit, and stops at 2,000", async () => {
    mockAdvisor();
    render(<AdvisorScreen />);
    const box = await screen.findByLabelText("Ask about your money");

    expect(box).toHaveAttribute("maxLength", "2000");
    await userEvent.type(box, "a");
    expect(screen.queryByText(/\/ 2,000/)).not.toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste("a".repeat(1850));
    expect(screen.getByText("1,850 / 2,000")).toBeInTheDocument();
  });

  it("says so when the advisor cannot be reached at all", async () => {
    mockAdvisor();
    mockFailure("/api/advisor/status");

    render(<AdvisorScreen />);

    expect(await screen.findByText("The advisor is unavailable")).toBeInTheDocument();
  });

  it("shows an empty list plainly", async () => {
    mockAdvisor({ list: [] });

    render(<AdvisorScreen />);

    expect(await screen.findByText("No conversations yet.")).toBeInTheDocument();
  });
});

describe("the nav", () => {
  it("puts Advisor between Cards and Import, active on /advisor", () => {
    render(<Nav />);

    const labels = NAV_ITEMS.map((item) => item.label);
    expect(labels.indexOf("Advisor")).toBe(labels.indexOf("Cards") + 1);
    expect(labels.indexOf("Import")).toBe(labels.indexOf("Advisor") + 1);
    expect(screen.getByRole("link", { name: "Advisor" })).toHaveAttribute("aria-current", "page");
  });
});
