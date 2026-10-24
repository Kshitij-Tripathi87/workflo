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

// The vendored wheel set comes from vendor/manifest.json, which
// scripts/build-wheels.py generates at pack time — no second hardcoded list
// to drift out of sync with the CLI's dependencies.
const vendor = path.join(pkgRoot, "vendor");
const actual = fs.existsSync(vendor) ? fs.readdirSync(vendor) : [];
const manifestPath = path.join(vendor, "manifest.json");
check("vendor/manifest.json exists", fs.existsSync(manifestPath));

let WHEELS = [];
try {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  WHEELS = manifest.wheels.map((w) => path.basename(w));
} catch {
  WHEELS = [];
}
check("manifest lists wheels", WHEELS.length > 0);

for (const w of WHEELS) {
  check(`vendor/${w}`, actual.includes(w));
}
const strays = actual.filter((f) => f.endsWith(".whl") && !WHEELS.includes(f));
check("no stray wheels", strays.length === 0, strays.join(", "));
check(
  `wheel count == ${WHEELS.length}`,
  actual.filter((f) => f.endsWith(".whl")).length === WHEELS.length
);
// Dependency order: the CLI is last, so every internal dist it requires is
// already in the venv when pip resolves it.
check("CLI wheel installed last", /^workflo_cli-/.test(WHEELS[WHEELS.length - 1] || ""));

if (failures > 0) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll package checks passed.");
