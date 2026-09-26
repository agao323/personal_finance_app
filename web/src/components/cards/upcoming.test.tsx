import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UpcomingPanel } from "@/components/cards/upcoming";
import { mockCards, server, upcoming } from "@/test/msw";

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
  try {
    globalThis.localStorage?.clear();
  } catch {
    // Not every environment has one. The panel is built to cope, so the test is too.
  }
});

describe("UpcomingPanel", () => {
  it("defaults to 90 days, so an annual credit is visible without asking", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/perks/upcoming", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(upcoming);
      }),
    );

    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    await waitFor(() => expect(urls).toHaveLength(1));
    expect(new URL(urls[0]).searchParams.get("within_days")).toBe("90");
  });

  it("changes the request when the horizon changes", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/perks/upcoming", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(upcoming);
      }),
    );

    render(<UpcomingPanel onChange={() => {}} revision={0} />);
    await waitFor(() => expect(urls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "30 days" }));

    await waitFor(() => expect(urls).toHaveLength(2));
    expect(new URL(urls[1]).searchParams.get("within_days")).toBe("30");
  });

  it("separates what is running out from what has plenty of time", async () => {
    // Grouping comes from the API's own is_urgent flag, which is per cadence.
    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByRole("heading", { name: "Running out" })).toBeInTheDocument();
  });

  it("takes urgency from the API rather than recomputing a threshold", async () => {
    // The travel credit has 3 days left but the API reports it as NOT urgent here. The
    // panel must follow the flag — if it computed its own threshold it would disagree,
    // and the two would drift the first time the rule changed.
    server.use(
      http.get("/api/perks/upcoming", () =>
        HttpResponse.json({
          ...upcoming,
          urgent_cents: 0,
          perks: [
            {
              ...upcoming.perks[0],
              perk: {
                ...upcoming.perks[0].perk,
                current_period: { ...upcoming.perks[0].perk.current_period!, is_urgent: false },
              },
            },
          ],
        }),
      ),
    );

    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByRole("heading", { name: "Plenty of time" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Running out" })).toBeNull();
  });

  it("reports the urgent subtotal separately from the total", async () => {
    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByText(/running out/)).toBeInTheDocument();
    expect(screen.getByText(/available/)).toBeInTheDocument();
  });

  it("names the card each credit belongs to", async () => {
    // A credit without its card is not actionable.
    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByText(/Sapphire Reserve/)).toBeInTheDocument();
  });

  it("says so when nothing is left, without reading as an error", async () => {
    server.use(
      http.get("/api/perks/upcoming", () =>
        HttpResponse.json({ ...upcoming, total_cents: 0, urgent_cents: 0, perks: [] }),
      ),
    );

    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByText(/Nothing left to use in this window/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports a failed load rather than an empty panel", async () => {
    server.use(
      http.get("/api/perks/upcoming", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    render(<UpcomingPanel onChange={() => {}} revision={0} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this");
  });

  it("marks a credit used from the panel", async () => {
    const onChange = vi.fn();
    render(<UpcomingPanel onChange={onChange} revision={0} />);
    await screen.findByText("Travel credit");

    const rows = screen.getAllByRole("listitem");
    await userEvent.click(within(rows[0]).getByRole("button", { name: "Mark used" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });
});
