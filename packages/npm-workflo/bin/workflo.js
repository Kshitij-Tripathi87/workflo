#!/usr/bin/env node
const path = require("path");
const { spawnSync } = require("child_process");

const venvDir = path.join(__dirname, "..", ".venv");
const bin = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "workflo.exe")
  : path.join(venvDir, "bin", "workflo");

const result = spawnSync(bin, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status ?? 1);