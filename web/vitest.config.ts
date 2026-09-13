import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./client/src/test/setup.ts"],
    include: [
      "client/src/**/*.test.{ts,tsx}",
      "server/tests/**/*.test.ts",
    ],
    coverage: {
      reporter: ["text", "html"],
    },
  },
});
