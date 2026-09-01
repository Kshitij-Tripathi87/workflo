#!/usr/bin/env python
"""Build the six internal wheels into vendor/ for the @workflo/qa npm shim.

Run from anywhere:
    python scripts/build-wheels.py

Steps:
  1. Wipe vendor/*.whl (never ship stale pre-rename wheels).
  2. Build each internal package with `python -m build --wheel`, in
     dependency order.
  3. Copy the produced wheel into vendor/ and verify it exists.

Dependency order matters only for install-time resolution clarity; each
wheel is self-describing, but we keep the canonical order here so the
postinstall list and this build list can never drift apart.

Requires: the `build` package (pip install build) and network access to
PyPI for isolated build environments.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Script lives at <repo>/packages/npm-workflo/scripts/.
PKG_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PKG_ROOT.parent.parent
VENDOR_DIR = PKG_ROOT / "vendor"
DIST_DIR = PKG_ROOT / "dist"

# (repo-relative dir, expected dist-name) in install order.
PACKAGES = [
    ("packages/workflo-schema", "workflo_schema"),
    ("packages/sandbox-isolation", "sandbox_isolation"),
    ("packages/probe-engine", "workflo_probe_engine"),
    ("apps/sandbox-executor", "workflo_executor"),
    ("packages/cortex-auth", "cortex_auth"),
    ("apps/workflo-cli", "workflo_cli"),
]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def ensure_build_module() -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "build", "--version"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail(
            "The 'build' package is required: pip install build\n"
            "Then re-run: python scripts/build-wheels.py"
        )


def wipe_vendor() -> None:
    VENDOR_DIR.mkdir(exist_ok=True)
    wiped = 0
    for whl in VENDOR_DIR.glob("*.whl"):
        whl.unlink()
        wiped += 1
    # Also clear old tarballs so dist/ never mixes versions.
    if DIST_DIR.exists():
        for tgz in DIST_DIR.glob("*.tgz"):
            tgz.unlink()
            wiped += 1
    print(f"  wiped {wiped} stale artifact(s)")


def build_wheel(rel_dir: str, dist_name: str) -> Path:
    pkg_dir = REPO_ROOT / rel_dir
    pyproject = pkg_dir / "pyproject.toml"
    if not pyproject.exists():
        fail(f"missing {pyproject} — repo layout changed?")

    print(f"  building {rel_dir} ...")
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(pkg_dir / "dist")],
        cwd=pkg_dir,
    )
    if proc.returncode != 0:
        fail(f"build failed for {rel_dir}")

    wheels = sorted((pkg_dir / "dist").glob(f"{dist_name}-*-py3-none-any.whl"))
    if not wheels:
        fail(
            f"no wheel matching {dist_name}-*-py3-none-any.whl in "
            f"{pkg_dir / 'dist'} — dist name drifted from pyproject?"
        )
    # If multiple versions accumulated, take the newest by mtime.
    return max(wheels, key=lambda p: p.stat().st_mtime)


def main() -> None:
    print("build-wheels: building @cortex/workflo vendor wheels")
    ensure_build_module()
    print("[1/3] wiping vendor/")
    wipe_vendor()

    print(f"[2/3] building {len(PACKAGES)} wheels")
    built: list[Path] = []
    for rel_dir, dist_name in PACKAGES:
        whl = build_wheel(rel_dir, dist_name)
        built.append(whl)

    print("[3/3] copying to vendor/")
    for whl in built:
        dest = VENDOR_DIR / whl.name
        shutil.copy2(whl, dest)
        if not dest.exists():
            fail(f"copy failed: {whl} -> {dest}")
        print(f"  {dest.relative_to(PKG_ROOT)}")

    print(f"\nOK: {len(built)} wheels vendored. Next:")
    print("  npm pack --pack-destination dist")
    print("  npm install -g dist/cortex-workflo-<version>.tgz")


if __name__ == "__main__":
    main()
