import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/test/msw";

// MSW intercepts at the network layer, so components run their real fetch path.
// `onUnhandledRequest: "error"` makes a forgotten mock a loud failure rather than a
// silent hang that looks like a slow test.
// Node 26 defines a `localStorage` global that is unavailable without
// --localstorage-file, and it shadows the one jsdom would otherwise provide, so
// `window.localStorage` is undefined here. Install an in-memory Storage so tests
// exercise the component's persistence logic rather than routing around it.
if (!globalThis.localStorage) {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size;
      },
    } satisfies Storage,
  });
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
