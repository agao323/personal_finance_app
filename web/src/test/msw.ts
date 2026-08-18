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

/**
 * Two years of month-end history, generated relative to today.
 *
 * Relative rather than hardcoded because the chart's range presets are computed from
 * the current date: a fixture pinned to 2026 would fall outside "last 3 months" the
 * moment the clock moved, and the alternative — fake timers around Testing Library —
 * fights `waitFor` for no benefit. The values are a straight line, so any test
 * asserting a specific number can derive it from this array rather than restating it.
 */
function monthlyPoints(count: number): ResponseOf<"/net-worth/series", "get">["points"] {
  const today = new Date();
  return Array.from({ length: count }, (_, index) => {
    const month = new Date(
      Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - (count - 1 - index), 1),
    );
    // Deliberately unround: the dashboard renders both the tiles and the chart's
    // table view, and a series value that happened to equal a tile's would make
    // `getByText` ambiguous in tests that are about neither.
    const assets_cents = 11_820_000 + index * 143_000;
    const liabilities_cents = 3_150_000 - index * 21_000;
    // 014 added this: how many accounts at this point are using a balance carried
    // forward past the 90-day cap. Zero throughout here — a fixture with fresh
    // balances everywhere. Tests about stale rendering set it explicitly.
    return {
      as_of: month.toISOString().slice(0, 10),
      assets_cents,
      liabilities_cents,
      net_worth_cents: assets_cents - liabilities_cents,
      stale_account_count: 0,
    };
  });
}

export const netWorthSeries: ResponseOf<"/net-worth/series", "get"> = {
  interval: "month",
  view: "mine",
  points: monthlyPoints(25),
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

/**
 * The series endpoint, honouring `from` so range switching is actually exercised
 * rather than asserted against a handler that ignores the query it was sent.
 */
export function mockNetWorthSeries(
  overrides: Partial<ResponseOf<"/net-worth/series", "get">> = {},
) {
  server.use(
    http.get("/api/net-worth/series", ({ request }) => {
      const params = new URL(request.url).searchParams;
      const view = params.get("view") ?? "mine";
      const from = params.get("from");
      const body = { ...netWorthSeries, view, ...overrides };
      return HttpResponse.json({
        ...body,
        points: from ? body.points.filter((point) => point.as_of >= from) : body.points,
      });
    }),
  );
}

export function mockRunway(overrides: Partial<ResponseOf<"/runway", "get">> = {}) {
  server.use(http.get("/api/runway", () => HttpResponse.json({ ...runway, ...overrides })));
}

export function mockFailure(path: string, status = 500) {
  server.use(http.get(path, () => HttpResponse.json({ detail: "boom" }, { status })));
}
