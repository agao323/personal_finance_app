/**
 * Browser-side API client.
 *
 * Every call is a **relative** path against this origin, handled by the proxy at
 * `src/app/api/[...path]/route.ts`. There is deliberately no API base URL here and
 * no `NEXT_PUBLIC_API_URL` anywhere in `web/` — the browser must not know that the
 * API exists as a separate service. See docs/ARCHITECTURE.md#request-path.
 */

export type QueryValue = string | number | boolean | null | undefined;

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
 * Rejects absolute URLs rather than passing them through: an absolute origin here
 * is the exact mistake the architecture is built to prevent, and failing loudly in
 * development is much cheaper than discovering it after deploy.
 */
export function apiPath(path: string, query?: Record<string, QueryValue>): string {
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

/**
 * Fetch JSON from the API through the proxy.
 *
 * Returns `unknown` on purpose. Ticket 005 generates `api-types.ts` from the API's
 * OpenAPI schema and callers narrow against it; hand-written response types are
 * exactly the drift this project is designed to make impossible.
 */
export async function apiFetch(
  path: string,
  options: { query?: Record<string, QueryValue> } & RequestInit = {},
): Promise<unknown> {
  const { query, ...init } = options;
  const response = await fetch(apiPath(path, query), {
    ...init,
    headers: { accept: "application/json", ...init.headers },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      // Non-JSON error body — the status line is all we have.
    }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}
