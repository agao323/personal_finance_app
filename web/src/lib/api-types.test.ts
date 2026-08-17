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
