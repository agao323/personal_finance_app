import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardsIndexPage from "./page";
import { CardsContext } from "@/components/cards/context";
import { cards, mockCards, server } from "@/test/msw";

function renderIndex(
  state: Partial<React.ComponentProps<typeof CardsContext.Provider>["value"]> = {},
) {
  return render(
    <CardsContext.Provider
      value={{
        cards,
        pending: false,
        refreshing: false,
        error: null,
        reload: () => {},
        revision: 0,
        ...state,
      }}
    >
      <CardsIndexPage />
    </CardsContext.Provider>,
  );
}

beforeEach(() => {
  mockCards();
  vi.stubGlobal("location", {
    origin: "https://allofmymoney.com",
    href: "https://allofmymoney.com/cards",
    pathname: "/cards",
  });
});

describe("cards index", () => {
  it("shows the cross-card view of what is running out", async () => {
    // It still has a home — just not in the way of the per-card work, which is the
    // common case.
    renderIndex();

    expect(await screen.findByText("Available to use")).toBeInTheDocument();
  });

  it("prompts you to pick a card", () => {
    renderIndex();

    expect(screen.getByText(/Pick a card/)).toBeInTheDocument();
  });

  it("says what to do first when there are no cards at all", () => {
    renderIndex({ cards: [] });

    expect(screen.getByText(/Add a credit card account/)).toBeInTheDocument();
  });

  it("reports a failed upcoming load rather than an empty panel", async () => {
    server.use(
      http.get("/api/perks/upcoming", () => HttpResponse.json({ detail: "no" }, { status: 500 })),
    );

    renderIndex();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this");
  });
});
