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

/**
 * Spend fixtures.
 *
 * Two levels, because the spending screen's whole shape is the drill from a parent
 * to its children: `parentSpend` is what `group_by=parent_category` returns and
 * `leafSpend` what `group_by=category` returns over the same window, with the leaf
 * buckets' `parent_id` linking them. Totals match between the two, as the API's do.
 */
export const parentSpend: ResponseOf<"/spend", "get"> = {
  start: "2026-08-01",
  end: "2026-08-18",
  group_by: "parent_category",
  total_cents: 500_000,
  excluded_transfer_count: 2,
  buckets: [
    {
      category_id: 6,
      category_name: "Housing",
      parent_id: null,
      spend_cents: 250_000,
      prior_period_cents: 240_000,
      change_cents: 10_000,
    },
    {
      category_id: 10,
      category_name: "Food",
      parent_id: null,
      spend_cents: 150_000,
      prior_period_cents: 170_000,
      change_cents: -20_000,
    },
    {
      category_id: null,
      category_name: "Uncategorised",
      parent_id: null,
      spend_cents: 100_000,
      prior_period_cents: 60_000,
      change_cents: 40_000,
    },
  ],
};

export const leafSpend: ResponseOf<"/spend", "get"> = {
  start: "2026-08-01",
  end: "2026-08-18",
  group_by: "category",
  total_cents: 500_000,
  excluded_transfer_count: 2,
  buckets: [
    {
      category_id: 7,
      category_name: "Rent or Mortgage",
      parent_id: 6,
      spend_cents: 220_000,
      prior_period_cents: 220_000,
      change_cents: 0,
    },
    {
      category_id: 11,
      category_name: "Groceries",
      parent_id: 10,
      spend_cents: 90_000,
      prior_period_cents: 100_000,
      change_cents: -10_000,
    },
    {
      category_id: 12,
      category_name: "Restaurants",
      parent_id: 10,
      spend_cents: 60_000,
      prior_period_cents: 70_000,
      change_cents: -10_000,
    },
    {
      category_id: 8,
      category_name: "Utilities",
      parent_id: 6,
      spend_cents: 30_000,
      prior_period_cents: 20_000,
      change_cents: 10_000,
    },
    {
      category_id: null,
      category_name: "Uncategorised",
      parent_id: null,
      spend_cents: 100_000,
      prior_period_cents: 60_000,
      change_cents: 40_000,
    },
  ],
};

/** Answers by `group_by`, so a drill-down test exercises the real request. */
export function mockSpend(
  overrides: Partial<ResponseOf<"/spend", "get">> = {},
  leafOverrides: Partial<ResponseOf<"/spend", "get">> = {},
) {
  server.use(
    http.get("/api/spend", ({ request }) => {
      const groupBy = new URL(request.url).searchParams.get("group_by");
      return groupBy === "category"
        ? HttpResponse.json({ ...leafSpend, ...leafOverrides })
        : HttpResponse.json({ ...parentSpend, ...overrides });
    }),
  );
}

export const transactions: ResponseOf<"/transactions", "get">["items"] = [
  {
    id: 1,
    account_id: 1,
    account_name: "Checking",
    posted_at: "2026-08-14",
    amount_cents: -4_512,
    merchant: "Corner Market",
    description: "CORNER MKT #21",
    category: { id: 11, name: "Groceries", parent_id: 10, kind: "expense" },
    category_source: "rule",
    transfer_group_id: null,
  },
  {
    id: 2,
    account_id: 1,
    account_name: "Checking",
    posted_at: "2026-08-09",
    amount_cents: -12_800,
    merchant: "Unknown Vendor",
    description: null,
    category: null,
    category_source: null,
    transfer_group_id: null,
  },
  {
    id: 3,
    account_id: 2,
    account_name: "Credit card",
    posted_at: "2026-08-03",
    amount_cents: 2_000,
    merchant: "Corner Market",
    description: "refund",
    category: { id: 11, name: "Groceries", parent_id: 10, kind: "expense" },
    category_source: "manual",
    transfer_group_id: null,
  },
];

/** Honours `category_id` and `uncategorised`, so a drill-down asserts the filter. */
export function mockTransactions(rows: ResponseOf<"/transactions", "get">["items"] = transactions) {
  server.use(
    http.get("/api/transactions", ({ request }) => {
      const params = new URL(request.url).searchParams;
      const categoryId = params.get("category_id");
      const uncategorised = params.get("uncategorised");
      let items = rows;
      if (uncategorised === "true") items = rows.filter((row) => row.category === null);
      else if (categoryId) items = rows.filter((row) => row.category?.id === Number(categoryId));
      return HttpResponse.json({
        items,
        page: { total: items.length, limit: 200, offset: 0 },
      });
    }),
  );
}
