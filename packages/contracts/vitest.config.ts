import { defineConfig } from "vitest/config";

// A local config keeps vitest from walking up to the monorepo root config,
// which is written for the legacy Vite/Express app and imports packages this
// workspace does not depend on (that made `pnpm test` fail at startup).
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
