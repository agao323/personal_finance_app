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
    account_name: "Savings",
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

/**
 * Accounts fixtures.
 *
 * Built around the cases the accounts screens exist to get right: a 50%-owned asset
 * where adjusted and raw differ, a stale balance, and a closed account carrying no
 * balance at all. Group subtotals are the API's, not a sum of the rows — the server
 * rounds once per account, and a fixture that re-added the rows would encode the
 * wrong arithmetic as the expected answer.
 */
export const accounts: ResponseOf<"/accounts", "get"> = {
  total_cents: 47_795_499,
  adjusted_total_cents: 24_922_058,
  groups: [
    {
      kind: "liquid_asset",
      total_cents: 4_451_740,
      adjusted_total_cents: 4_451_740,
      accounts: [
        {
          id: 1,
          name: "Checking",
          kind: "liquid_asset",
          subtype: "checking",
          source: "csv",
          currency: "USD",
          institution: { id: 1, name: "Meridian Bank" },
          balance_cents: 137_717,
          adjusted_balance_cents: 137_717,
          balance_as_of: "2026-08-01",
          current_stake_bps: 10_000,
          is_stale: false,
          closed_at: null,
        },
        {
          id: 2,
          name: "Savings",
          kind: "liquid_asset",
          subtype: "savings",
          source: "manual",
          currency: "USD",
          institution: { id: 1, name: "Meridian Bank" },
          balance_cents: 4_314_023,
          adjusted_balance_cents: 4_314_023,
          balance_as_of: "2026-01-04",
          current_stake_bps: 10_000,
          is_stale: true,
          closed_at: null,
        },
      ],
    },
    {
      kind: "illiquid_asset",
      total_cents: 45_088_082,
      adjusted_total_cents: 22_544_041,
      accounts: [
        {
          id: 3,
          name: "Rental property",
          kind: "illiquid_asset",
          subtype: "real_estate",
          source: "manual",
          currency: "USD",
          institution: null,
          balance_cents: 45_088_082,
          adjusted_balance_cents: 22_544_041,
          balance_as_of: "2026-08-01",
          current_stake_bps: 5_000,
          is_stale: false,
          closed_at: null,
        },
        {
          id: 4,
          name: "Old car",
          kind: "illiquid_asset",
          subtype: "vehicle",
          source: "manual",
          currency: "USD",
          institution: null,
          balance_cents: null,
          adjusted_balance_cents: null,
          balance_as_of: null,
          current_stake_bps: 10_000,
          is_stale: false,
          closed_at: "2026-01-01",
        },
      ],
    },
    {
      kind: "liability",
      total_cents: 29_580_000,
      adjusted_total_cents: 17_748_000,
      accounts: [
        {
          id: 5,
          name: "Mortgage",
          kind: "liability",
          subtype: "mortgage",
          source: "manual",
          currency: "USD",
          institution: { id: 1, name: "Meridian Bank" },
          balance_cents: 29_580_000,
          adjusted_balance_cents: 17_748_000,
          balance_as_of: "2026-08-01",
          current_stake_bps: 6_000,
          is_stale: false,
          closed_at: null,
        },
      ],
    },
  ],
};

export function mockAccounts(overrides: Partial<ResponseOf<"/accounts", "get">> = {}) {
  server.use(http.get("/api/accounts", () => HttpResponse.json({ ...accounts, ...overrides })));
}

/** A 50%-owned account with a mid-history stake change — the case worth rendering. */
export const accountDetail: ResponseOf<"/accounts/{account_id}", "get"> = {
  id: 3,
  name: "Rental property",
  kind: "illiquid_asset",
  subtype: "real_estate",
  source: "manual",
  currency: "USD",
  institution: { id: 2, name: "Harbour Trust" },
  balance_cents: 45_088_082,
  adjusted_balance_cents: 22_544_041,
  balance_as_of: "2026-08-01",
  is_stale: false,
  current_stake_bps: 5_000,
  closed_at: null,
  stakes: [
    {
      id: 10,
      owner_user_id: 1,
      owner_display_name: "Owner",
      percentage_bps: 10_000,
      effective_from: "2024-03-01",
      effective_to: "2025-06-01",
    },
    {
      id: 11,
      owner_user_id: 1,
      owner_display_name: "Owner",
      percentage_bps: 5_000,
      effective_from: "2025-06-01",
      effective_to: null,
    },
  ],
};

export const accountHistory: ResponseOf<"/accounts/{account_id}/history", "get"> = {
  account_id: 3,
  points: [
    { as_of: "2026-06-01", balance_cents: 44_000_000, source: "manual", is_stale: false },
    { as_of: "2026-07-01", balance_cents: 44_500_000, source: "manual", is_stale: false },
    { as_of: "2026-08-01", balance_cents: 45_088_082, source: "manual", is_stale: false },
  ],
};

export function mockAccountDetail(
  overrides: Partial<ResponseOf<"/accounts/{account_id}", "get">> = {},
  historyOverrides: Partial<ResponseOf<"/accounts/{account_id}/history", "get">> = {},
) {
  server.use(
    http.get("/api/accounts/:id/history", () =>
      HttpResponse.json({ ...accountHistory, ...historyOverrides }),
    ),
    http.get("/api/accounts/:id", () => HttpResponse.json({ ...accountDetail, ...overrides })),
  );
}

/**
 * The category taxonomy, in the API's order: parents before their own children.
 *
 * Includes an income and a transfer category deliberately — a picker built from
 * `/spend` would have neither, and "this was a transfer" is the correction the
 * transactions screen exists to make.
 */
export const categories: ResponseOf<"/categories", "get"> = [
  { id: 6, name: "Housing", parent_id: null, kind: "expense" },
  { id: 10, name: "Food", parent_id: null, kind: "expense" },
  { id: 1, name: "Income", parent_id: null, kind: "income" },
  { id: 30, name: "Transfer", parent_id: null, kind: "transfer" },
  { id: 8, name: "Utilities", parent_id: 6, kind: "expense" },
  { id: 11, name: "Groceries", parent_id: 10, kind: "expense" },
  { id: 12, name: "Restaurants", parent_id: 10, kind: "expense" },
  { id: 2, name: "Salary", parent_id: 1, kind: "income" },
  { id: 31, name: "Credit Card Payment", parent_id: 30, kind: "transfer" },
];

export function mockCategories(rows: ResponseOf<"/categories", "get"> = categories) {
  server.use(http.get("/api/categories", () => HttpResponse.json(rows)));
}

/**
 * A paginated `/transactions` that honours every filter the screen sends.
 *
 * Filtering in the handler rather than returning a fixed list is what makes the
 * filter tests mean anything — against a handler that ignored its query they would
 * pass with the filters wired to nothing.
 */
export function mockTransactionList(
  rows: ResponseOf<"/transactions", "get">["items"] = transactions,
) {
  server.use(
    http.get("/api/transactions", ({ request }) => {
      const params = new URL(request.url).searchParams;
      let items = rows;

      const from = params.get("from");
      const to = params.get("to");
      const accountId = params.get("account_id");
      const categoryId = params.get("category_id");
      const uncategorised = params.get("uncategorised");
      const search = params.get("search");

      if (from) items = items.filter((row) => row.posted_at >= from);
      if (to) items = items.filter((row) => row.posted_at <= to);
      if (accountId) items = items.filter((row) => row.account_id === Number(accountId));
      if (categoryId) items = items.filter((row) => row.category?.id === Number(categoryId));
      if (uncategorised === "true") items = items.filter((row) => row.category === null);
      if (uncategorised === "false") items = items.filter((row) => row.category !== null);
      if (search) {
        const needle = search.toLowerCase();
        items = items.filter((row) =>
          `${row.merchant ?? ""} ${row.description ?? ""}`.toLowerCase().includes(needle),
        );
      }

      const limit = Number(params.get("limit") ?? 50);
      const offset = Number(params.get("offset") ?? 0);
      return HttpResponse.json({
        items: items.slice(offset, offset + limit),
        page: { total: items.length, limit, offset },
      });
    }),
  );
}

/** The write endpoints the transactions screen uses, all succeeding. */
export function mockTransactionWrites() {
  server.use(
    http.patch("/api/transactions/:id", async ({ request }) => {
      const body = (await request.json()) as { category_id: number | null };
      return HttpResponse.json({ ...transactions[0], category_id: body.category_id });
    }),
    http.post("/api/transactions/bulk-categorise", async ({ request }) => {
      const body = (await request.json()) as { transaction_ids: number[] };
      return HttpResponse.json({ updated: body.transaction_ids.length });
    }),
    http.post("/api/transactions/bulk-transfer", async ({ request }) => {
      const body = (await request.json()) as { transaction_ids: number[] };
      return HttpResponse.json({
        transfer_group_id: "group-1",
        updated: body.transaction_ids.length,
      });
    }),
  );
}

/** A CSV preview: one new row, one unchanged, one that failed to parse. */
export const csvPreview: ResponseOf<"/import/csv/preview", "post"> = {
  account_id: 1,
  detected_mapping: {
    posted_at: "Date",
    amount: "Amount",
    merchant: "Description",
    description: null,
    external_id: null,
    invert_amount: false,
  },
  mapping_source: "detected",
  will_create: 1,
  will_update: 1,
  will_skip: 1,
  errors: ["1 of 3 rows have errors and would be skipped"],
  rows: [
    {
      row_number: 2,
      action: "create",
      posted_at: "2026-08-14",
      amount_cents: -4_512,
      merchant: "Corner Market",
      description: null,
      external_id: "a1",
      errors: [],
    },
    {
      row_number: 3,
      action: "update",
      posted_at: "2026-08-09",
      amount_cents: -12_800,
      merchant: "Unknown Vendor",
      description: null,
      external_id: "a2",
      errors: [],
    },
    {
      row_number: 4,
      action: "skip",
      posted_at: null,
      amount_cents: null,
      merchant: null,
      description: null,
      external_id: null,
      errors: ["could not read the date '31/02/2026'"],
    },
  ],
};

/** Honours a supplied mapping, so a re-preview after an edit actually differs. */
export function mockCsvImport(overrides: Partial<typeof csvPreview> = {}) {
  server.use(
    http.post("/api/import/csv/preview", async ({ request }) => {
      const form = await request.formData();
      const supplied = form.get("mapping");
      if (typeof supplied === "string") {
        const mapping = JSON.parse(supplied) as typeof csvPreview.detected_mapping;
        return HttpResponse.json({
          ...csvPreview,
          ...overrides,
          detected_mapping: mapping,
          mapping_source: "supplied",
          // A flipped sign turns the outflows into inflows.
          rows: csvPreview.rows.map((row) =>
            row.amount_cents === null || row.amount_cents === undefined || !mapping.invert_amount
              ? row
              : { ...row, amount_cents: -row.amount_cents },
          ),
        });
      }
      return HttpResponse.json({ ...csvPreview, ...overrides });
    }),
    http.post("/api/import/csv/commit", () =>
      HttpResponse.json({ created: 1, updated: 1, skipped: 1, errors: [] }),
    ),
  );
}

export const rules: ResponseOf<"/rules", "get"> = [
  {
    id: 1,
    pattern: "CORNER MARKET",
    match_type: "contains",
    category_id: 11,
    category_name: "Groceries",
    priority: 100,
  },
  {
    id: 2,
    pattern: "^AMZN",
    match_type: "regex",
    category_id: 21,
    category_name: "Shopping",
    priority: 200,
  },
];

export function mockRules(rows: ResponseOf<"/rules", "get"> = rules) {
  // A mutable copy, so a reorder or delete is visible on the next GET — against a
  // fixed list those tests would pass with the handlers wired to nothing.
  let current = [...rows];
  server.use(
    http.get("/api/rules", () => HttpResponse.json(current)),
    http.post("/api/rules", async ({ request }) => {
      const body = (await request.json()) as { pattern: string; category_id: number };
      const created = {
        id: 99,
        pattern: body.pattern,
        match_type: "contains" as const,
        category_id: body.category_id,
        category_name: "Groceries",
        priority: 300,
      };
      current = [...current, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch("/api/rules/:id", async ({ params, request }) => {
      const body = (await request.json()) as { priority?: number };
      const id = Number(params.id);
      current = current.map((rule) =>
        rule.id === id && body.priority !== undefined ? { ...rule, priority: body.priority } : rule,
      );
      return HttpResponse.json(current.find((rule) => rule.id === id));
    }),
    http.delete("/api/rules/:id", ({ params }) => {
      current = current.filter((rule) => rule.id !== Number(params.id));
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("/api/rules/apply", () =>
      HttpResponse.json({ examined: 120, categorised: 8, manual_preserved: 3 }),
    ),
    http.post("/api/rules/preview", async ({ request }) => {
      const body = (await request.json()) as { pattern: string };
      if (body.pattern === "(a+)+b") {
        return HttpResponse.json({ detail: "pattern backtracks exponentially" }, { status: 422 });
      }
      const matches = body.pattern.toLowerCase().includes("corner")
        ? transactions.filter((row) => row.merchant?.toLowerCase().includes("corner"))
        : [];
      return HttpResponse.json({
        match_count: matches.length,
        already_manual: matches.filter((row) => row.category_source === "manual").length,
        matches,
      });
    }),
  );
}

export const sessionRead: ResponseOf<"/auth/session", "get"> = {
  user_id: 1,
  email: "owner@example.invalid",
  display_name: "Owner",
};

export function mockSession(overrides: Partial<ResponseOf<"/auth/session", "get">> = {}) {
  server.use(
    http.get("/api/auth/session", () => HttpResponse.json({ ...sessionRead, ...overrides })),
  );
}

export function mockNoSession() {
  server.use(
    http.get("/api/auth/session", () =>
      HttpResponse.json({ detail: "Not signed in" }, { status: 401 }),
    ),
  );
}

export const members: ResponseOf<"/members", "get"> = [
  {
    id: 1,
    email: "owner@example.invalid",
    display_name: "Owner",
    is_active: true,
  },
  {
    id: 2,
    email: "partner@example.invalid",
    display_name: "Partner",
    is_active: true,
  },
];

/** Mutable, so adding or deactivating is visible on the next read. */
export function mockMembers(rows: ResponseOf<"/members", "get"> = members) {
  let current = [...rows];
  server.use(
    http.get("/api/members", () => HttpResponse.json(current)),
    http.post("/api/members", async ({ request }) => {
      const body = (await request.json()) as { email: string; display_name: string };
      const created = {
        id: 99,
        email: body.email,
        display_name: body.display_name,
        is_active: true,
      };
      current = [...current, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch("/api/members/:id", async ({ params, request }) => {
      const body = (await request.json()) as { is_active?: boolean };
      const id = Number(params.id);
      current = current.map((m) =>
        m.id === id && body.is_active !== undefined ? { ...m, is_active: body.is_active } : m,
      );
      return HttpResponse.json(current.find((m) => m.id === id));
    }),
  );
}

// ── cards and perks (051) ────────────────────────────────────────────────────

/** Two perks on one card: one used, one expiring in three days. */
export const cards: ResponseOf<"/cards", "get"> = [
  {
    account_id: 1,
    name: "Sapphire Reserve",
    institution: "Chase",
    is_closed: false,
    unused_cents: 30_000,
    perks: [
      {
        id: 1,
        account_id: 1,
        name: "Travel credit",
        description: null,
        value_cents: 30_000,
        cadence: "annual",
        anchor_on: "2026-01-01",
        is_active: true,
        current_period: {
          start: "2026-01-01",
          end: "2027-01-01",
          days_remaining: 3,
          is_used: false,
          used_note: null,
        },
      },
      {
        id: 2,
        account_id: 1,
        name: "Dining credit",
        description: null,
        value_cents: 2_500,
        cadence: "monthly",
        anchor_on: "2026-01-01",
        is_active: true,
        current_period: {
          start: "2026-06-01",
          end: "2026-07-01",
          days_remaining: 12,
          is_used: true,
          used_note: null,
        },
      },
    ],
  },
];

export const upcoming: ResponseOf<"/perks/upcoming", "get"> = {
  within_days: 45,
  as_of: "2026-06-18",
  total_cents: 30_000,
  perks: [{ perk: cards[0].perks[0], account_id: 1, card_name: "Sapphire Reserve" }],
};

/** Mutable, so marking a perk used is visible on the next read. */
export function mockCards(
  rows: ResponseOf<"/cards", "get"> = cards,
  soon: ResponseOf<"/perks/upcoming", "get"> = upcoming,
) {
  const current = structuredClone(rows);
  let soonest = structuredClone(soon);

  const setUsed = (perkId: number, used: boolean) => {
    for (const card of current) {
      for (const perk of card.perks) {
        if (perk.id === perkId && perk.current_period) perk.current_period.is_used = used;
      }
    }
    soonest = { ...soonest, perks: soonest.perks.filter((p) => p.perk.id !== perkId || !used) };
  };

  server.use(
    http.get("/api/cards", () => HttpResponse.json(current)),
    http.get("/api/perks/upcoming", () => HttpResponse.json(soonest)),
    http.post("/api/perks/:id/redemptions", ({ params }) => {
      setUsed(Number(params.id), true);
      return HttpResponse.json(current[0].perks[0]);
    }),
    http.delete("/api/perks/:id/redemptions", ({ params }) => {
      setUsed(Number(params.id), false);
      return HttpResponse.json(current[0].perks[0]);
    }),
    http.post("/api/cards/:id/perks", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: 99, account_id: 1, ...body }, { status: 201 });
    }),
  );
}
