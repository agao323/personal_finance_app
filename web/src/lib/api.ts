/**
 * Browser-side API client, typed from the generated contract.
 *
 * Every call is a **relative** path against this origin, handled by the proxy at
 * `src/app/api/[...path]/route.ts`. There is deliberately no API base URL here and
 * no `NEXT_PUBLIC_API_URL` anywhere in `web/` — the browser must not know the API
 * exists as a separate service. See docs/ARCHITECTURE.md#request-path.
 *
 * Path and response type are inferred from the route string, so a typo in a URL or
 * a wrong assumption about a response shape is a compile error rather than a
 * runtime surprise. Never hand-write a response type; run `make types`.
 */

import type { paths } from "./api-types";

export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";

/**
 * Route strings that support `M`.
 *
 * openapi-typescript emits unimplemented verbs as `put?: never` rather than omitting
 * them, so testing for key presence matches everything. Requiring `responses` is what
 * actually distinguishes a real operation.
 */
export type PathsWith<M extends HttpMethod> = {
  [P in keyof paths]: paths[P] extends { [K in M]: infer Operation }
    ? Operation extends { responses: unknown }
      ? P
      : never
    : never;
}[keyof paths];

/** The JSON body of the success response for `P` + `M`. */
export type ResponseOf<P extends keyof paths, M extends HttpMethod> = paths[P][M] extends {
  responses: infer R;
}
  ? R extends { 200: { content: { "application/json": infer Body } } }
    ? Body
    : R extends { 201: { content: { "application/json": infer Body } } }
      ? Body
      : void
  : never;

/** The declared query parameters for `P` + `M`, if it takes any. */
export type QueryOf<P extends keyof paths, M extends HttpMethod> = paths[P][M] extends {
  parameters: { query?: infer Q };
}
  ? Q
  : never;

/** The declared request body for `P` + `M`, if it takes one. */
export type BodyOf<P extends keyof paths, M extends HttpMethod> = paths[P][M] extends {
  requestBody: { content: { "application/json": infer B } };
}
  ? B
  : never;

export type QueryValue = string | number | boolean | null | undefined;

export type PathParams = Record<string, string | number>;

/**
 * Substitute `{name}` placeholders in a templated route.
 *
 * Templated routes (`/accounts/{account_id}`) have to stay literal at the call site,
 * because that literal is what `ResponseOf` infers the response type from. Building
 * the URL by interpolation and casting the result back to the template type would
 * discard exactly the guarantee this module exists to provide.
 *
 * A missing parameter throws rather than leaving the placeholder in the URL: a
 * request to `/accounts/%7Baccount_id%7D` comes back 404 or 422, and the resulting
 * bug report is about the wrong thing entirely.
 */
export function fillPath(template: string, params: PathParams = {}): string {
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => {
    const value = params[name];
    if (value === undefined || value === null) {
      throw new Error(`Missing path parameter "${name}" for ${template}`);
    }
    return encodeURIComponent(String(value));
  });
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/**
 * Build a relative API path.
 *
 * Rejects absolute URLs rather than passing them through: an absolute origin here is
 * the exact mistake the architecture exists to prevent, and failing loudly in
 * development is much cheaper than discovering it after deploy.
 */
export function apiPath(path: string, query?: Record<string, QueryValue> | null): string {
  if (/^[a-z]+:\/\//i.test(path)) {
    throw new Error(
      `apiFetch takes a relative path, got an absolute URL: ${path}. The browser must ` +
        `never address the API directly — see docs/ARCHITECTURE.md#request-path.`,
    );
  }

  const normalised = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.append(key, String(value));
  }
  const search = params.toString();
  return `/api${normalised}${search ? `?${search}` : ""}`;
}

type Options<P extends keyof paths, M extends HttpMethod> = {
  method?: M;
  signal?: AbortSignal;
  headers?: HeadersInit;
  /** Values for any `{name}` placeholders in the route. */
  params?: PathParams;
} & ([QueryOf<P, M>] extends [never] ? { query?: never } : { query?: QueryOf<P, M> }) &
  ([BodyOf<P, M>] extends [never] ? { body?: never } : { body: BodyOf<P, M> });

/**
 * Fetch JSON from the API through the proxy.
 *
 * ```ts
 * const ready = await apiFetch("/ready");                        // ReadyResponse
 * await apiFetch("/accounts", { method: "post", body: { … } });  // body is typed
 * await apiFetch("/accounts/{account_id}", { params: { account_id: 7 } });
 * ```
 *
 * `M` defaults to `"get"`, so read calls need no type arguments; for other verbs it
 * is inferred from `options.method`.
 */
export async function apiFetch<M extends HttpMethod = "get", P extends PathsWith<M> = PathsWith<M>>(
  path: P,
  options: Options<P & keyof paths, M> = {} as Options<P & keyof paths, M>,
): Promise<ResponseOf<P & keyof paths, M>> {
  const { method = "get", query, body, headers, signal, params } = options;

  const url = apiPath(fillPath(path as string, params), query as Record<string, QueryValue>);
  const response = await fetch(url, {
    method: method.toUpperCase(),
    signal,
    headers: {
      accept: "application/json",
      ...(body === undefined ? {} : { "content-type": "application/json" }),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const errorBody: unknown = await response.json();
      if (errorBody && typeof errorBody === "object" && "detail" in errorBody) {
        detail = String((errorBody as { detail: unknown }).detail);
      }
    } catch {
      // Non-JSON error body — the status line is all we have.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as ResponseOf<P & keyof paths, M>;
  return (await response.json()) as ResponseOf<P & keyof paths, M>;
}
