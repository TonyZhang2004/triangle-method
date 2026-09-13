import { defineConfig } from "vitest/config";

/** Run gateway tests independently from the browser test setup. */
export default defineConfig({
  test: {
    environment: "node",
    include: ["server/tests/**/*.test.ts"],
  },
});
