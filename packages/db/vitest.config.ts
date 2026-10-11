import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globalSetup: ["./tests/global-setup.ts"],
    hookTimeout: 300_000,
    testTimeout: 120_000,
    pool: "forks",
    // Tests share one embedded cluster + database; fixtures must use random
    // UUIDs per test (they do) so parallel files cannot collide.
    sequence: { concurrent: false },
  },
});
