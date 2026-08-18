import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// .mts so Vite loads this as real ESM. `__dirname` does not exist here — that is the
// point of the extension, and Vite warns about (then eventually rejects) a .ts config
// containing ESM syntax.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    // jsdom refuses localStorage on an opaque origin (about:blank), so anything
    // reading a persisted preference throws. Give it a real origin.
    environmentOptions: { jsdom: { url: "http://localhost:3000" } },
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Next.js build output and E2E specs are not vitest's business.
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
  },
});
