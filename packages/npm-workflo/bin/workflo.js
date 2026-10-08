#!/usr/bin/env node
/**
 * @cortex/workflo entry shim.
 *
 * The Python engine lives in a package-local venv created by postinstall.
 * This shim verifies it exists, forwards argv + stdio + exit code.
 * If the engine is missing (partial install, cleaned node_modules),
 * instructs the user to rebuild instead of failing silently.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const venvDir = path.join(__dirname, "..", ".venv");
const bin =
  process.platform === "win32"
    ? path.join(venvDir, "Scripts", "workflo.exe")
    : path.join(venvDir, "bin", "workflo");

if (!fs.existsSync(bin)) {
  console.error(
    "✖ workflo engine not found at:\n  " + bin +
    "\n\nThe install did not complete. Rebuild it with:" +
    "\n  npm rebuild -g @cortex/workflo" +
    "\n\nRequires Python >= 3.11 on PATH."
  );
  process.exit(1);
}

const result = spawnSync(bin, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status ?? 1);
