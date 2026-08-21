const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const pkgRoot = __dirname.replace(/scripts$/, "");
const venvDir = path.join(pkgRoot, ".venv");

function run(cmd, options = {}) {
  execSync(cmd, { stdio: "inherit", cwd: pkgRoot, ...options });
}

// Ensure Python 3.11+ is available
try {
  execSync("python3 --version", { stdio: "ignore" });
} catch {
  console.error(
    "workflo requires Python 3.11+ on PATH. Install it, then re-run `npm install -g workflo`."
  );
  process.exit(1);
}

console.log("Installing workflo...");
console.log("  → Setting up environment...");
run(`python3 -m venv "${venvDir}"`);

const pip = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "pip.exe")
  : path.join(venvDir, "bin", "pip");

// The five internal packages in dependency order, as .whl files in vendor/.
// pip installs each wheel and resolves its PyPI dependencies; the vendor/
// wheels are included as a cache, so if a transitive dep is already present
// it won't be re-downloaded.
const wheels = [
  "vendor/tenant_shield_schema-0.1.0-py3-none-any.whl",
  "vendor/airlock_sandbox_isolation-0.1.0-py3-none-any.whl",
  "vendor/workflo_executor-0.1.0-py3-none-any.whl",
  "vendor/workflo_probe_engine-0.1.0-py3-none-any.whl",
  "vendor/workflo_cli-0.1.0-py3-none-any.whl",
];

console.log("  → Installing packages...");
for (const whl of wheels) {
  const whlPath = path.join(pkgRoot, whl);
  if (!fs.existsSync(whlPath)) {
    console.error(`✖ Missing wheel: ${whl}`);
    process.exit(1);
  }
  run(`"${pip}" install --quiet "${whlPath}"`);
}

console.log("✓ workflo installed");
console.log(
  "  Run: workflo run --repo <repo-url> --test --security --output receipt.json"
);