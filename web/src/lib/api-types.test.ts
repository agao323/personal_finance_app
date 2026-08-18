/**
 * Contract tests.
 *
 * Most of the value here is at compile time: `make lint` runs `tsc --noEmit` over
 * this file, so the declarations below fail the build if the generated contract loses
 * a path, renames a field, or widens a type. That is the mechanism keeping the three
 * Wave 2 lanes honest — a frontend session cannot write a component against a shape
 * the backend never built.
 *
 * Exported deliberately: an exported binding is "used", which keeps the assertions
 * here without suppressing unused-variable lint.
 */

import { describe, expect, it } from "vitest";

import type { ResponseOf } from "@/lib/api";
import type { components, paths } from "@/lib/api-types";

// ── compile-time ─────────────────────────────────────────────────────────────

/** The routes 003 shipped must exist and must be real operations, not `never`. */
export type HealthGet = paths["/health"]["get"]["responses"][200];
export type ReadyGet = paths["/ready"]["get"]["responses"][200];

/** `/ready` documents its 503 — a caller has to be able to see the failure case. */
export type ReadyUnavailable = paths["/ready"]["get"]["responses"][503];

/** Response bodies resolve to the Pydantic models, not `unknown`. */
export const health: ResponseOf<"/health", "get"> = { status: "ok" };
export const ready: ResponseOf<"/ready", "get"> = { status: "ok", database: true };

/** The generated component schemas are reachable by name. */
export const readySchema: components["schemas"]["ReadyResponse"] = {
  status: "unavailable",
  database: false,
};

/**
 * `status` is a literal union, not a bare string — proof that FastAPI's `Literal`
 * survived the pipeline. If this ever widens, `@ts-expect-error` becomes unused and
 * `tsc` fails, so the guarantee cannot rot silently.
 */
// @ts-expect-error "degraded" is not a member of the status union
export const invalidStatus: ResponseOf<"/health", "get"> = { status: "degraded" };

/** Verbs the API does not implement are `never`, so they cannot be called. */
export const noPostOnReady: paths["/ready"]["post"] = undefined;

// ── runtime ──────────────────────────────────────────────────────────────────

describe("generated contract", () => {
  it("carries the response shapes the API returns", () => {
    expect(health).toEqual({ status: "ok" });
    expect(ready).toEqual({ status: "ok", database: true });
    expect(readySchema.database).toBe(false);
  });

  it("declares no POST on /ready", () => {
    expect(noPostOnReady).toBeUndefined();
  });

  it("would reject an out-of-contract status at compile time", () => {
    // The value exists at runtime; the assertion that matters already happened in tsc.
    expect(invalidStatus).toEqual({ status: "degraded" });
  });
});

// ── the Wave 2 freeze ─────────────────────────────────────────────────────────
//
// Everything below is the point of ticket 012: Lane C can write these types today,
// against endpoints Lane A and Lane B have not implemented. If a backend session
// changes a response model without re-freezing, `make types-check` fails in CI and
// these lines stop compiling — which is the drift being designed out.

/** Every v1 route the frontend will call is already in the contract. */
export type FrozenPaths =
  | paths["/net-worth"]["get"]
  | paths["/net-worth/series"]["get"]
  | paths["/spend"]["get"]
  | paths["/runway"]["get"]
  | paths["/accounts"]["get"]
  | paths["/accounts/{account_id}"]["get"]
  | paths["/transactions"]["get"]
  | paths["/rules"]["get"];

/** Money is integer cents, so a component can format without guessing units. */
export const netWorth: ResponseOf<"/net-worth", "get"> = {
  as_of: "2026-08-18",
  view: "mine",
  net_worth_cents: 12_345_678,
  assets_cents: 15_000_000,
  liabilities_cents: 2_654_322,
  breakdown: [{ kind: "liquid_asset", total_cents: 5_000_000 }],
  stale_account_ids: [],
};

/** Ownership percentages are basis points: 5000 is 50.00%. */
export const stake: components["schemas"]["StakeRead"] = {
  id: 1,
  owner_user_id: 1,
  owner_display_name: "Owner",
  percentage_bps: 5000,
  effective_from: "2026-01-01",
  effective_to: null,
};

/** The view toggle is a literal union, not a string — a typo is a compile error. */
// @ts-expect-error "everyone" is not a member of ViewScope
export const badView: components["schemas"]["ViewScope"] = "everyone";

/** Writes are typed too: apiFetch infers the body from the route. */
export type CreateAccountBody =
  paths["/accounts"]["post"]["requestBody"]["content"]["application/json"];

export const newAccount: CreateAccountBody = {
  name: "Checking",
  kind: "liquid_asset",
  subtype: "checking",
};

describe("wave 2 contract freeze", () => {
  it("exposes money as integer cents", () => {
    expect(netWorth.net_worth_cents).toBe(12_345_678);
  });

  it("exposes ownership as basis points", () => {
    expect(stake.percentage_bps).toBe(5000);
  });

  it("types a write body from the route string", () => {
    expect(newAccount.kind).toBe("liquid_asset");
  });

  it("rejects an out-of-contract view at compile time", () => {
    expect(badView).toBe("everyone");
  });
});
