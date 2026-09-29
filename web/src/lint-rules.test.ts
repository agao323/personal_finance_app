// @vitest-environment node
/**
 * The project's own lint rules, tested like any other guard: each one against code that
 * breaks it (must report) and code that follows it (must not). A rule that never fires
 * looks exactly like one that is broken. See docs/FRONTEND.md#layers.
 *
 * Lints strings through ESLint's API with this directory's real `eslint.config.mjs`, so a
 * config change that silently disables a rule fails here.
 */

import path from "node:path";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint({ cwd: path.resolve(import.meta.dirname, "..") });

async function reported(
  code: string,
  filePath: string,
): Promise<{ rule: string; message: string }[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages
    .filter((m) => m.ruleId !== null)
    .map((m) => ({ rule: m.ruleId as string, message: m.message }));
}

async function rules(code: string, filePath: string): Promise<string[]> {
  return (await reported(code, filePath)).map((m) => m.rule);
}

const FETCH = "no-restricted-globals";
const FETCH_PROPERTY = "no-restricted-properties";
const TYPES_ONLY = "@typescript-eslint/no-restricted-imports";

describe("one fetcher", () => {
  it("rejects fetch() in a component", async () => {
    const code = 'export async function load() {\n  return fetch("/api/ready");\n}\n';
    expect(await rules(code, "src/components/example.ts")).toContain(FETCH);
  });

  it("rejects window.fetch and globalThis.fetch", async () => {
    const code =
      'export const a = () => window.fetch("/api/a");\nexport const b = () => globalThis.fetch("/api/b");\n';
    const found = await rules(code, "src/components/example.ts");
    expect(found.filter((rule) => rule === FETCH_PROPERTY)).toHaveLength(2);
  });

  it("rejects fetch() in any route handler but the proxy", async () => {
    const code = 'export async function GET() {\n  return fetch("http://example.invalid");\n}\n';
    expect(await rules(code, "src/app/healthz/route.ts")).toContain(FETCH);
  });

  it("allows fetch() in lib/api.ts and the proxy route", async () => {
    const code = 'export async function go() {\n  return fetch("/api/ready");\n}\n';
    expect(await rules(code, "src/lib/api.ts")).not.toContain(FETCH);
    expect(await rules(code, "src/app/api/[...path]/route.ts")).not.toContain(FETCH);
  });

  it("says what the rule is, where it is documented, and how to fix it", async () => {
    const [first] = await reported("fetch('/x');\n", "src/components/example.ts");
    expect(first.message).toContain("apiFetch()");
    expect(first.message).toContain("docs/FRONTEND.md#layers");
  });
});

describe("api-types is imported as types only", () => {
  it("rejects a value import", async () => {
    const code = 'import { paths } from "@/lib/api-types";\nexport const p = paths;\n';
    expect(await rules(code, "src/components/example.ts")).toContain(TYPES_ONLY);
  });

  it("rejects a relative value import", async () => {
    const code = 'import { components } from "./api-types";\nexport const c = components;\n';
    expect(await rules(code, "src/lib/example.ts")).toContain(TYPES_ONLY);
  });

  it("allows `import type`", async () => {
    const code =
      'import type { components } from "@/lib/api-types";\nexport type Card = components["schemas"]["CardRead"];\n';
    expect(await rules(code, "src/components/example.ts")).not.toContain(TYPES_ONLY);
  });

  it("says how to fix it", async () => {
    const code = 'import { paths } from "@/lib/api-types";\nexport const p = paths;\n';
    const messages = (await reported(code, "src/components/example.ts")).filter(
      (m) => m.rule === TYPES_ONLY,
    );
    expect(messages[0].message).toContain("import type");
    expect(messages[0].message).toContain("make types");
  });
});
