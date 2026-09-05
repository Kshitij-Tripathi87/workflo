#!/usr/bin/env node
/**
 * @cortex/workflo postinstall — set up the Python sidecar venv.
 *
 * What it does:
 *   1. Detect a Python >= 3.11 interpreter (python3 / python / py -3).
 *      On failure prints an OS-specific install hint and exits non-zero.
 *   2. Create <pkgRoot>/.venv and install the six vendored wheels in
 *      dependency order. Transitive deps resolve from PyPI — this is the
 *      ONE network call at install time (documented in the README).
 *   3. Write .workflo-install.json marker so re-installs are skipped when
 *      nothing changed (package version, Python version, wheel contents).
 *
 * Failure policy: every failure prints an actionable message and exits
 * non-zero. There are no silent partial installs.
 */

const { execFileSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const pkgRoot = path.join(__dirname, "..");
const venvDir = path.join(pkgRoot, ".venv");
const markerPath = path.join(pkgRoot, ".workflo-install.json");

// The six internal wheels, in dependency install order. Keep in sync with
// scripts/build-wheels.py (same list, same order).
const WHEELS = [
  "vendor/workflo_schema-1.1.1-py3-none-any.whl",
  "vendor/sandbox_isolation-1.1.1-py3-none-any.whl",
  "vendor/workflo_probe_engine-1.1.1-py3-none-any.whl",
  "vendor/workflo_executor-1.1.1-py3-none-any.whl",
  "vendor/cortex_auth-1.1.1-py3-none-any.whl",
  "vendor/workflo_cli-1.1.1-py3-none-any.whl",
];

function fail(msg) {
  console.error(`\n✖ workflo postinstall failed: ${msg}`);
  process.exit(1);
}

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, { stdio: ["ignore", "pipe", "pipe"], ...opts });
}

function tryRun(cmd, args) {
  try {
    return { ok: true, out: run(cmd, args).toString() };
  } catch (e) {
    return { ok: false, err: e };
  }
}

// ---- 1. Python detection --------------------------------------------------

function pythonHint() {
  if (process.platform === "win32") {
    return [
      "",
      "Install Python 3.11+ and re-run the install:",
      "  winget install --id Python.Python.3.12",
      "or download from https://www.python.org/downloads/",
    ].join("\n");
    }
  if (process.platform === "darwin") {
    return [
      "",
      "Install Python 3.11+ and re-run the install:",
      "  brew install python@3.12",
      "or download from https://www.python.org/downloads/",
    ].join("\n");
  }
  return [
    "",
    "Install Python 3.11+ using your package manager and re-run the install, e.g.:",
    "  sudo apt-get install python3.12   # Debian/Ubuntu",
    "  sudo dnf install python3.12       # Fedora",
    "or download from https://www.python.org/downloads/",
  ].join("\n");
}

function findPython() {
  const candidates =
    process.platform === "win32"
      ? [["py", ["-3"]], ["python", []], ["python3", []]]
      : [["python3", []], ["python", []], ["py", ["-3"]]];

  for (const [cmd, prefix] of candidates) {
    const probe = tryRun(cmd, [...prefix, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"]);
    if (!probe.ok) continue;
    const version = tryRun(cmd, [...prefix, "--version"]);
    return { cmd, prefix, version: version.ok ? version.out.trim() : "unknown" };
  }
  return null;
}

// ---- 2/3. venv + wheels ----------------------------------------------------

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function wheelFingerprints() {
  return WHEELS.map((rel) => {
    const abs = path.join(pkgRoot, rel);
    if (!fs.existsSync(abs)) fail(`missing vendored wheel: ${rel} (broken npm package?)`);
    return sha256File(abs);
  });
}

function desiredMarker(pyVersion, fingerprints) {
  return JSON.stringify(
    {
      version: require(path.join(pkgRoot, "package.json")).version,
      pythonVersion: pyVersion,
      wheelFingerprints: fingerprints,
    },
    null,
    2
  );
}

function venvPaths(pythonCmd, pythonPrefix) {
  // Recreate the venv with the detected interpreter.
  run(pythonCmd, [...pythonPrefix, "-m", "venv", venvDir]);
  const pip =
    process.platform === "win32"
      ? path.join(venvDir, "Scripts", "pip.exe")
      : path.join(venvDir, "bin", "pip");
  if (!fs.existsSync(pip)) fail(`venv created but pip not found at ${pip}`);
  return pip;
}

function main() {
  console.log("@cortexstudio/workflo postinstall: setting up Python engine...");

  // Fast path: everything already installed and unchanged?
  let pyVersion = null;
  const fingerprints = wheelFingerprints();
  if (fs.existsSync(markerPath)) {
    const py = findPython();
    if (py) {
      pyVersion = py.version;
      try {
        if (fs.readFileSync(markerPath, "utf8") === desiredMarker(pyVersion, fingerprints)) {
          console.log("✓ workflo engine already installed (marker match) — skipping.");
          return;
        }
      } catch {
        // unreadable marker -> fall through to full reinstall
      }
    }
  }

  const py = findPython();
  if (!py) {
    fail(`no Python >= 3.11 found on PATH.${pythonHint()}`);
  }
  pyVersion = py.version;
  console.log(`  using ${py.version} (${[py.cmd, ...py.prefix].join(" ")})`);

  // Rebuild the venv from scratch whenever the marker does not match:
  // mixing old wheels/editables into an existing venv is how stale-install
  // bugs happen. Deterministic > fast.
  if (fs.existsSync(venvDir)) {
    fs.rmSync(venvDir, { recursive: true, force: true, maxRetries: 3 });
  }
  console.log("  creating venv...");
  const pip = venvPaths(py.cmd, py.prefix);

  console.log("  installing wheels (transitive deps come from PyPI)...");
  for (const rel of WHEELS) {
    const abs = path.join(pkgRoot, rel);
    try {
      run(pip, ["install", "--quiet", abs], { stdio: ["ignore", "ignore", "inherit"] });
    } catch (e) {
      fail(
        `pip install failed for ${rel}: ${e.message}\n`
        + "  Transitive dependencies are fetched from PyPI at install time;\n"
        + "  check network/proxy access and retry: npm rebuild @cortexstudio/workflo"
      );
    }
  }

  fs.writeFileSync(markerPath, desiredMarker(pyVersion, fingerprints));
  console.log("✓ workflo engine installed");
  console.log("  Run: workflo auth login     # first-run authentication");
  console.log("       workflo run --repo <repo-url> --test   # needs Docker running");
}

main();
