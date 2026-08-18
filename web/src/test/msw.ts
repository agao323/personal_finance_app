/**
 * MSW server and typed fixtures.
 *
 * Fixtures are typed from `api-types.ts`, which is the point of ticket 012: these
 * shapes are generated from the same Pydantic models the backend implements against,
 * so a mock cannot describe a response the API will never send. If a backend session
 * changes a model without re-freezing, these stop compiling.
 */

import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import type { ResponseOf } from "@/lib/api";

export const server = setupServer();

export const netWorth: ResponseOf<"/net-worth", "get"> = {
  as_of: "2026-08-18",
  view: "mine",
  net_worth_cents: 12_345_678,
  assets_cents: 15_000_000,
  liabilities_cents: 2_654_322,
  breakdown: [
    { kind: "liquid_asset", total_cents: 5_000_000 },
    { kind: "illiquid_asset", total_cents: 10_000_000 },
    { kind: "liability", total_cents: 2_654_322 },
  ],
  stale_account_ids: [],
};

export const runway: ResponseOf<"/runway", "get"> = {
  liquid_assets_cents: 5_000_000,
  windows: [
    { months: 3, average_monthly_spend_cents: 520_000, months_of_runway: 9.6 },
    { months: 6, average_monthly_spend_cents: 500_000, months_of_runway: 10.0 },
    { months: 12, average_monthly_spend_cents: 480_000, months_of_runway: 10.4 },
  ],
  partial_month_excluded: true,
};

export function mockNetWorth(
  overrides: Partial<ResponseOf<"/net-worth", "get">> = {},
  priorOverrides: Partial<ResponseOf<"/net-worth", "get">> | null = {},
) {
  server.use(
    http.get("/api/net-worth", ({ request }) => {
      const asOf = new URL(request.url).searchParams.get("as_of");
      const view = new URL(request.url).searchParams.get("view") ?? "mine";
      if (asOf) {
        if (priorOverrides === null) return new HttpResponse(null, { status: 404 });
        return HttpResponse.json({
          ...netWorth,
          net_worth_cents: 11_000_000,
          ...priorOverrides,
        });
      }
      return HttpResponse.json({ ...netWorth, view, ...overrides });
    }),
  );
}

export function mockRunway(overrides: Partial<ResponseOf<"/runway", "get">> = {}) {
  server.use(http.get("/api/runway", () => HttpResponse.json({ ...runway, ...overrides })));
}

export function mockFailure(path: string, status = 500) {
  server.use(http.get(path, () => HttpResponse.json({ detail: "boom" }, { status })));
}
