import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    hookTimeout: 120_000,
    testTimeout: 90_000,
    pool: "forks",
    sequence: { concurrent: false },
  },
});
