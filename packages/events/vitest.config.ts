import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globalSetup: ["./tests/global-setup.ts"],
    hookTimeout: 300_000,
    testTimeout: 120_000,
    pool: "forks",
    sequence: { concurrent: false },
  },
});
