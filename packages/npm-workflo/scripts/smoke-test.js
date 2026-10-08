#!/usr/bin/env node
/**
 * Package smoke test: verifies the npm tarball's structural invariants
 * without touching Python. Run via `npm test` inside packages/npm-workflo.
 */
const fs = require("fs");
const path = require("path");

const pkgRoot = path.join(__dirname, "..");
let failures = 0;

function check(name, ok, detail) {
  if (ok) {
    console.log(`  ok  ${name}`);
  } else {
    failures++;
    console.error(`FAIL  ${name}${detail ? " — " + detail : ""}`);
  }
}

// bin shim present and parses (strip shebang: not valid in Function bodies)
const binPath = path.join(pkgRoot, "bin", "workflo.js");
check("bin/workflo.js exists", fs.existsSync(binPath));
const strip = (src) => src.replace(/^#![^\n]*/, "");
new Function(strip(fs.readFileSync(binPath, "utf8"))); // syntax check

// postinstall + build scripts parse
for (const s of ["scripts/postinstall.js", "scripts/build-wheels.py"]) {
  const p = path.join(pkgRoot, s);
  check(`${s} exists`, fs.existsSync(p));
}
new Function(strip(fs.readFileSync(path.join(pkgRoot, "scripts", "postinstall.js"), "utf8")));

// exactly the six expected wheels vendored — no pre-rename strays
const WHEELS = [
  "workflo_schema-1.1.1-py3-none-any.whl",
  "sandbox_isolation-1.1.1-py3-none-any.whl",
  "workflo_probe_engine-1.1.1-py3-none-any.whl",
  "workflo_executor-1.1.1-py3-none-any.whl",
  "cortex_auth-1.1.1-py3-none-any.whl",
  "workflo_cli-1.1.1-py3-none-any.whl",
];
const vendor = path.join(pkgRoot, "vendor");
const actual = fs.existsSync(vendor) ? fs.readdirSync(vendor) : [];
for (const w of WHEELS) {
  check(`vendor/${w}`, actual.includes(w));
}
const strays = actual.filter((f) => f.endsWith(".whl") && !WHEELS.includes(f));
check("no stray wheels", strays.length === 0, strays.join(", "));
check(
  "wheel count == 6",
  actual.filter((f) => f.endsWith(".whl")).length === 6
);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll package checks passed.");
