import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globalSetup: ["./tests/global-setup.ts"],
    hookTimeout: 180_000,
    testTimeout: 180_000,
    pool: "forks",
    sequence: { concurrent: false },
    fileParallelism: false,
  },
});
