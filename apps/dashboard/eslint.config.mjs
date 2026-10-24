import { FlatCompat } from "@eslint/eslintrc";

// `next lint` is deprecated (removed in Next 16) and drove the ESLint 9
// incompatibility that made `pnpm check` fail: Next loaded the hoisted
// ESLint 9 while passing ESLint 8 `ESLint()` options. Linting now runs the
// ESLint CLI against this flat config, which loads the unchanged Next
// shareable config through FlatCompat.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  { ignores: [".next/**", "next-env.d.ts", "node_modules/**"] },
  ...compat.extends("next/core-web-vitals"),
];

export default config;
