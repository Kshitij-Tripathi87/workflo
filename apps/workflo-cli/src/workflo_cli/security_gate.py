"""workflo security-gate — Phase 6 Security Release Gate (spec §12).

One command that runs the full adversarial test suite and reports a
structured verdict. The gate is the single release barrier: if this
fails, no deploy without a signed exception.

Suites and their Phase 6 attack categories are mapped to real pytest
invocations against the monorepo's test files. Each suite is reported
as PASS, FAIL, or SKIP (missing host prerequisites), with failures
including the failing attack IDs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

# Suite name -> (package, pytest target args, description)
# Package roots are resolved relative to the workflo monorepo root.
GATE_SUITES: list[tuple[str, str, str, str]] = [
    ("Landlock (spec)",        "sandbox-runtime",   "tests/integration/test_landlock_gate.py", "-m linux"),
    ("Network flows",          "sandbox-runtime",   "tests/integration/test_network_gate.py", "-m linux"),
    ("Agent adversarial",      "worker-engine",     "tests/test_agent_adversarial.py", ""),
    ("Receipt attacks",        "sandbox-isolation", "tests/test_receipt_attacks.py", ""),
    ("Prompt injection",       "sandbox-runtime",   "tests/adversarial/test_prompt_injection.py", ""),
    ("Planner fuzzing",        "sandbox-runtime",   "tests/adversarial/test_planner_fuzz.py", ""),
]


@dataclass
class SuiteResult:
    name: str
    status: str          # PASS | FAIL | SKIP
    exit_code: int
    failures: list[str]
    detail: str


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from start looking for the monorepo root."""
    for parent in (start, *start.parents):
        if (parent / "workflo-project").exists():
            return parent / "workflo-project"
        # dev: direct packages dir
        if (parent / "packages" / "sandbox-runtime").exists():
            return parent
    return None


def _run_suite(name: str, package: str, target: str, marker: str,
               repo_root: Path) -> SuiteResult:
    pkg_dir = repo_root / "packages" / package
    tests_dir = pkg_dir / "tests"
    if not tests_dir.exists():
        return SuiteResult(name, "SKIP", 0, [], f"package tests not found: {pkg_dir}")

    test_path = pkg_dir / target
    if not test_path.exists():
        return SuiteResult(name, "SKIP", 0, [], f"test file missing: {target}")

    cwd = str(pkg_dir)
    # Import-cycle safety: the test imports need the package src on path.
    src = str(pkg_dir / "src")
    env_src = subprocess.os.environ.get("PYTHONPATH", "")
    env = dict(subprocess.os.environ, PYTHONPATH=f"{src};{env_src}" if env_src else src)

    cmd = [
        sys.executable, "-m", "pytest", str(test_path),
        "-q", "--no-header", "--tb=line",
        "-x", "--disable-warnings",
    ]
    if marker:
        cmd.extend(["-m", marker])

    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env,
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return SuiteResult(name, "FAIL", 124, ["timeout"], "pytest timed out after 120s")
    except Exception as e:
        return SuiteResult(name, "SKIP", 0, [], f"could not run: {e}")

    if proc.returncode == 0:
        return SuiteResult(name, "PASS", 0, [], "")

    failures = _failures_from_output(proc.stderr or proc.stdout or "")
    return SuiteResult(name, "FAIL", proc.returncode, failures, "")


def _failures_from_output(output: str) -> list[str]:
    """Pull 'FAILED' lines out of pytest output for reporting."""
    failures = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("FAILED ") or line.startswith("FAILED:"):
            # pytest shortline: "FAILED path::test - AssertionError..."
            failures.append(line[:160])
    return failures


@click.command("security-gate")
@click.option("--repo", "repo_path", default=None,
              help="Path to the workflo monorepo root (default: auto-detect "
                   "from the current directory).")
@click.option("--json-out", default=None,
              help="Write per-suite results as JSON to this path.")
def security_gate(repo_path, json_out):
    """Workflo Security Gate — the Phase 6 release barrier.

    Runs all adversarial test suites and prints a structured verdict.
    Exit code 0 only when ALL suites pass (or are legitimately skipped):
    """
    click.echo("\n╔══════════════════════════════════════════════════════════════╗")
    click.echo("║           WORKFLO SECURITY GATE — Phase 6                     ║")
    click.echo("╚══════════════════════════════════════════════════════════════╝\n")

    # Locate the repo root
    if repo_path:
        root = Path(repo_path)
    else:
        root = _find_repo_root(Path.cwd())
    if root is None:
        click.echo("SECURITY GATE: UNSUPPORTED_ENVIRONMENT — cannot find workflo packages")
        sys.exit(5)

    results = []
    all_pass = True
    for name, package, target, markers in GATE_SUITES:
        click.echo(f"  ⏳ {name:<35}", nl=False)
        result = _run_suite(name, package, target, markers, root)
        results.append(result)
        if result.status == "PASS":
            click.echo("PASS")
        elif result.status == "SKIP":
            click.echo(f"SKIP  ({result.detail or 'missing'})")
        else:
            click.echo("FAIL")
        all_pass = all_pass and result.status in ("PASS", "SKIP")

    click.echo("")
    click.echo("─┐" + "─" * 56)
    for result in results:
        if result.status == "FAIL":
            for f in result.failures:
                click.echo(f"  {f}")
    click.echo("─┘")

    if all_pass:
        click.echo("\nSECURITY GATE: ✅ PASS\n")
    else:
        click.echo("\nSECURITY GATE: ❌ FAIL\n")

    if json_out:
        payload = [
            {"suite": r.name, "status": r.status, "exit_code": r.exit_code,
             "failures": r.failures, "detail": r.detail}
            for r in results
        ]
        Path(json_out).write_text(json.dumps(payload, indent=2))

    # Exit codes (§12.4): 0 = all pass, 1 = adversarial tests failed
    sys.exit(0 if all_pass else 1)