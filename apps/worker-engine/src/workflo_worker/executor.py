"""Test executor — runs pytest with the spec's markers and collects results.

Reads PROBE_GROUPS environment variable to determine which probe groups
to execute. Probe groups are composable: ["surface", "security"] etc.

For deep-test / aggressive-test tiers, this also:
  - Starts an in-container ModelServer (Ollama + Qwen2.5-Coder)
  - Feeds the repo file tree to the model with a budget
  - Parses the model's output into ProbeSpec objects (with one retry on parse failure)
  - Generates a pytest file from those ProbeSpecs and runs it alongside the surface tests
  - Stops the model server + wipes its on-disk state at teardown

The model stage is gated behind the flag — plain --test / --security never
boots Ollama. This keeps the base image small, fast, and free of model weights
for the 90% of runs that don't need them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from workflo_schema import RunSpec, RunSummary
from workflo_worker.model import (
    ModelOutputInvalid,
    ModelServer,
    ModelServerConfig,
    ModelServerError,
    build_correction_prompt,
    generate_from_model_output,
    wipe_model_state,
)
from workflo_worker.streamer import ResultStreamer
from workflo_worker.web.stage import run_web_stage
from workflo_worker.security.stage import run_security_stage


# Repo file tree budget — how many source lines we send to the model.
# This is the protection against "dump the whole repo into the prompt"
# the plan calls out. Qwen2.5-Coder 7B has a 32k token context; we leave
# plenty of headroom for the model's response and the system prompt.
MAX_REPO_LINES_FOR_MODEL = 4000
MAX_FILE_LINES_FOR_MODEL = 400
MAX_TOTAL_BYTES_FOR_MODEL = 256 * 1024  # 256KB of source code max


def execute_run(spec_dict: dict, streamer: ResultStreamer) -> RunSummary:
    """Execute a test run based on the spec and return the summary."""
    spec = RunSpec(**spec_dict)

    # Read probe groups from env (set by sandbox-executor)
    probe_groups = []
    env_probe_groups = os.environ.get("PROBE_GROUPS")
    if env_probe_groups:
        try:
            probe_groups = json.loads(env_probe_groups)
            if not isinstance(probe_groups, list):
                streamer.log(f"Warning: PROBE_GROUPS is not a list: {env_probe_groups}")
                probe_groups = ["surface", "security"]
        except (json.JSONDecodeError, TypeError):
            streamer.log(f"Warning: Failed to parse PROBE_GROUPS: {env_probe_groups}")
            probe_groups = ["surface", "security"]
    else:
        # Default fallback
        probe_groups = ["surface", "security"]

    # IMPORTANT: `spec.markers` here are workflo's internal probe-group labels
    # (e.g. ["surface"], ["deep", "security"]), NOT pytest markers. We must NOT
    # pass them as `-m` to pytest — that would deselect every test without an
    # explicit `@pytest.mark.surface` decorator, which is every test in any
    # repo that didn't anticipate workflo. Surface tests run the repo's full
    # native pytest collection, unfiltered.
    _ = spec.markers  # consumed for visibility only
    marker_arg: list[str] = []

    # Use mkstemp for secure temp file creation (mktemp is deprecated due to race conditions)
    results_fd, results_path_str = tempfile.mkstemp(suffix=".json", prefix="workflo-pytest-")
    os.close(results_fd)  # pytest will reopen it
    results_path = Path(results_path_str)

    streamer.log(f"Executing pytest with markers: (none — surface tier runs all tests)")
    streamer.log(f"Probe groups: {probe_groups}")

    # NOTE: pytest must run INSIDE the cloned repo so it picks up the local
    # conftest.py / pyproject.toml of the customer repo. We chdir into the
    # repo path forwarded by the executor.
    repo_path = os.environ.get("WORKFLO_REPO_PATH", "/workspace/repo")
    streamer.log(f"Working directory: {repo_path}")

    # ---- Offline install of the repo under test ----
    # Most real repos' tests `import <the package>`, and the sandbox has
    # NO network egress by design — so `pip install -e .` (which resolves
    # deps from PyPI) would fail. We attempt a network-free install:
    #   --no-deps            never touches the index (no dep resolution)
    #   --no-build-isolation uses the image's setuptools/wheel instead of
    #                        downloading a build backend
    # Works for dependency-free packages (click, etc.). If it fails, the
    # run continues and any collection failure is surfaced honestly below.
    install_error: Optional[str] = None
    if os.path.isdir(repo_path):
        try:
            install_proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-deps",
                 "--no-build-isolation", "--break-system-packages", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if install_proc.returncode != 0:
                install_error = install_proc.stderr[-500:].strip()
                streamer.log(f"Offline repo install failed (continuing): {install_error}")
            else:
                streamer.log("Offline repo install succeeded")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            install_error = f"{type(e).__name__}: {e}"
            streamer.log(f"Offline repo install skipped: {install_error}")
    else:
        streamer.log("Repo path missing — skipping offline install")

    # ---- Model stage (only for deep / aggressive tiers) ----
    model_findings = []
    model_inference_teardown: Optional[bool] = None
    model_inference_error: Optional[str] = None
    model_generated_tests_dir: Optional[Path] = None
    needs_model_stage = bool(set(probe_groups) & {"deep", "aggressive"})

    if needs_model_stage:
        model_inference_teardown, model_inference_error, model_findings, model_generated_tests_dir = (
            _run_model_stage(streamer, repo_path, probe_groups)
        )
        # Persist model stage status to host-side executor via stdout lines.
        # The executor parses WORKFLO_MODEL_TEARDOWN to populate the receipt's
        # model_inference_teardown field.
        model_status = {
            "teardown": model_inference_teardown,
            "error": model_inference_error,
            "findings_count": len(model_findings),
        }
        streamer.log(f"WORKFLO_MODEL_TEARDOWN: {json.dumps(model_status)}")

    # Use sys.executable -m pytest so pytest is found even when the
    # 'pytest' entry point isn't on PATH (common on Windows, and in
    # Docker when the PATH doesn't include the user site-packages bin dir).
    cmd = [sys.executable, "-m", "pytest", "-v", "--json-report", f"--json-report-file={results_path}"]
    cmd.extend(marker_arg)

    if spec.targets.include:
        cmd.extend(spec.targets.include)
    if spec.targets.exclude:
        for excl in spec.targets.exclude:
            cmd.extend(["--deselect", excl])

    env_overrides = spec.env
    streamer.log(f"env overrides: {env_overrides}")

    exec_env = os.environ.copy()
    exec_env.update(env_overrides)
    if "PYTHONPATH" in os.environ:
        entries = [str(Path(p).resolve()) for p in os.environ["PYTHONPATH"].split(os.pathsep) if p]
        exec_env["PYTHONPATH"] = os.pathsep.join(entries)

    proc = None
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_path,
            env=exec_env,
            capture_output=True,
            text=True,
            timeout=spec.config.timeout_seconds,
        )
        streamer.log(proc.stdout[-2000:] if proc.stdout else "(no stdout)")
        if proc.returncode != 0 and proc.stderr:
            streamer.log(f"[STDERR]\n{proc.stderr[-2000:]}")
    except FileNotFoundError:
        streamer.log("pytest not found in PATH")
    except subprocess.TimeoutExpired:
        streamer.log("Test run timed out")

    summary = _parse_results(results_path)

    # Honest collection accounting: pytest exits 1 when tests FAIL (a valid
    # outcome), but exits >=2 on collection/internal errors, or nonzero with
    # nothing collected. In both latter cases the repo's tests never really
    # ran — say so instead of reporting a clean 0/0.
    if proc is not None and proc.returncode >= 2:
        summary.collection_error = (
            f"pytest exited {proc.returncode} (collection/internal error)"
        )
    elif proc is not None and proc.returncode != 0 and summary.total == 0:
        summary.collection_error = (
            f"pytest exited {proc.returncode} with 0 tests collected"
        )
    if summary.collection_error and install_error:
        summary.collection_error += f"; offline repo install failed: {install_error}"
    elif summary.collection_error and proc is not None and proc.stderr:
        summary.collection_error += f"; stderr: {proc.stderr[-300:].strip()}"

    # Merge model findings into the report's findings so the receipt
    # surfaces what the model proposed. Pure addition — surface pytest
    # results stay in summary.
    if model_findings:
        summary.findings.extend(model_findings)

    # ---- Security stage (only for the security tier) ----
    # Runs AFTER pytest so a slow app bootstrap can't delay the pytest
    # results. The security stage uses the same app bootstrap primitive
    # as the web tier (start_app_under_test) but runs API-based security
    # probes (tenant isolation, etc.) instead of Playwright browser probes.
    if "security" in probe_groups:
        security_payload = run_security_stage(repo_path)
        streamer.log(f"WORKFLO_SECURITY_PROBES: {json.dumps(security_payload)}")

    # ---- Web stage (only for the web tier) ----
    # Runs AFTER pytest so a slow web bootstrap can't delay the pytest
    # results. The web image (workflo-worker-web) ships Playwright +
    # Chromium; on any other image this resolves to a no-op payload with
    # an app_start_error naming the missing config.
    if "web" in probe_groups:
        web_payload = run_web_stage(repo_path)
        streamer.log(f"WORKFLO_WEB_PROBES: {json.dumps(web_payload)}")

    # Emit workflo report format for executor to parse
    report_data = {
        "run_id": spec.model_dump().get("run_id") if hasattr(spec, "model_dump") else None,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "duration_seconds": summary.duration_seconds,
        "soc2_controls_covered": summary.soc2_controls,
        "collection_error": summary.collection_error,
        "findings": summary.findings,
    }
    streamer.log(f"WORKFLO_REPORT: {json.dumps(report_data)}")

    # Canary check — run FROM INSIDE the container so we can prove that
    # THIS container's network namespace actually has no egress, not the
    # host's. If this succeeds while --network none is set, isolation is
    # broken. The host-side executor parses this line and feeds it into
    # the receipt's canary_check field.
    canary_data = _run_canary_check()
    streamer.log(f"WORKFLO_CANARY: {json.dumps(canary_data)}")

    return summary


def _run_model_stage(
    streamer: ResultStreamer,
    repo_path: str,
    probe_groups: list[str],
) -> tuple[Optional[bool], Optional[str], list[dict], Optional[Path]]:
    """Run the model stage: start Ollama, get ProbeSpecs, stop + wipe.

    Returns:
        (model_inference_teardown, model_inference_error, findings, generated_tests_dir)
        - teardown is True if the model stage ran AND Ollama state was wiped
        - teardown is False if the model stage ran but wipe failed
        - teardown is None if the model stage never ran (caller didn't request it)
        - findings: structured findings from the model's probes (passed to receipt)
        - generated_tests_dir: pytest test file the worker wrote, so the executor
          could persist/audit it (None if model stage failed)
    """
    findings: list[dict] = []
    generated_tests_dir: Optional[Path] = None

    streamer.log("[model] starting Ollama server for deep-test analysis...")
    server = ModelServer(ModelServerConfig())
    try:
        server.start()
    except ModelServerError as e:
        streamer.log(f"[model] ERROR: could not start model server: {e}")
        return False, f"model server start failed: {e}", findings, None

    try:
        # Build the prompt from the repo's file tree (budget-limited)
        prompt = _build_repo_analysis_prompt(repo_path, probe_groups)
        streamer.log(f"[model] prompt built ({len(prompt)} chars)")

        # First attempt
        try:
            raw = server.generate(prompt)
            specs = generate_from_model_output(raw)
            streamer.log(f"[model] generated {len(specs)} valid probes (1st attempt)")
        except (ModelServerError, ModelOutputInvalid) as e:
            # ONE retry per the plan: re-prompt with parse error appended.
            streamer.log(f"[model] 1st attempt failed ({type(e).__name__}): {e}")
            try:
                raw_retry = server.generate(
                    build_correction_prompt(prompt, raw if 'raw' in dir() else "", str(e)),
                    timeout_seconds=60.0,
                )
                specs = generate_from_model_output(raw_retry)
                streamer.log(f"[model] generated {len(specs)} valid probes (2nd attempt)")
            except (ModelServerError, ModelOutputInvalid) as e2:
                streamer.log(f"[model] retry also failed: {e2}")
                return None, f"model output invalid after retry: {e2}", findings, None

        # Generate a pytest file from the ProbeSpecs and place it inside
        # the repo so pytest auto-discovers it.
        pytest_file = _write_pytest_from_specs(repo_path, specs)
        generated_tests_dir = pytest_file.parent
        streamer.log(f"[model] wrote pytest file: {pytest_file}")

        # Convert ProbeSpecs to findings for the receipt
        for spec in specs:
            findings.append({
                "name": spec.name,
                "pattern": spec.pattern,
                "path": spec.path,
                "method": spec.method,
                "expected_status": (
                    spec.expected_status if isinstance(spec.expected_status, int)
                    else sorted(spec.expected_status)
                ),
                "soc2_controls": spec.soc2_controls,
                "description": spec.description,
                "source": "model_inference",
            })

        # Stage complete — teardown happens below in finally.
        teardown_ok, teardown_error = _teardown_model_state(streamer)
        return teardown_ok, teardown_error, findings, generated_tests_dir

    finally:
        try:
            server.stop()
        except Exception as e:
            streamer.log(f"[model] ERROR stopping server: {e}")


def _teardown_model_state(streamer: ResultStreamer) -> tuple[bool, Optional[str]]:
    """Wipe Ollama state and return (success, error_string)."""
    try:
        wiped = wipe_model_state()
        if wiped:
            streamer.log("[model] state wiped successfully")
            return True, None
        else:
            err = "Ollama state still exists after wipe"
            streamer.log(f"[model] ERROR: {err}")
            return False, err
    except Exception as e:
        err = f"wipe_model_state raised: {type(e).__name__}: {e}"
        streamer.log(f"[model] ERROR: {err}")
        return False, err


def _build_repo_analysis_prompt(repo_path: str, probe_groups: list[str]) -> str:
    """Build a budget-limited prompt that summarizes the repo for the model.

    The model sees:
      - The directory tree (truncated)
      - The first N lines of each source file (truncated)
      - The probe group context (deep / aggressive / etc.)
      - The schema of the output we expect
    """
    repo = Path(repo_path)
    if not repo.exists():
        return f"Repo path {repo_path} does not exist."

    tree_lines: list[str] = []
    file_contents: list[str] = []
    total_bytes = 0

    # Walk the repo, skipping .git, __pycache__, build artifacts, etc.
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist", ".tox"}
    skip_ext = {".pyc", ".so", ".o", ".lock", ".png", ".jpg", ".gif", ".pdf", ".zip", ".tar", ".gz"}

    if repo.is_dir():
        for path in sorted(repo.rglob("*")):
            if path.is_dir():
                if path.name in skip_dirs:
                    continue
                rel = path.relative_to(repo)
                tree_lines.append(f"  {rel}/")
                continue

            if path.name.startswith(".") and path.name not in {".gitignore"}:
                continue

            if path.suffix in skip_ext:
                continue

            rel = path.relative_to(repo)
            tree_lines.append(f"  {rel}")

            # Read source files for the prompt body (not just tree)
            if path.suffix in {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".md"}:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue
                lines = content.splitlines()
                truncated = lines[:MAX_FILE_LINES_FOR_MODEL]
                snippet = "\n".join(truncated)
                if len(lines) > MAX_FILE_LINES_FOR_MODEL:
                    snippet += f"\n# ... ({len(lines) - MAX_FILE_LINES_FOR_MODEL} more lines truncated)"
                file_block = f"\n--- {rel} ({len(lines)} lines) ---\n{snippet}\n"
                if total_bytes + len(file_block) > MAX_TOTAL_BYTES_FOR_MODEL:
                    file_contents.append("\n--- (truncated: byte budget exhausted) ---\n")
                    break
                file_contents.append(file_block)
                total_bytes += len(file_block)

    tree_str = "\n".join(tree_lines[:200])  # cap tree size
    files_str = "".join(file_contents)

    tier = "deep" if "deep" in probe_groups else (
        "aggressive" if "aggressive" in probe_groups else "model-assisted"
    )

    return (
        f"You are a senior security engineer auditing a Python repo at `{repo_path}`.\n"
        f"The repo has been git-cloned into this sandbox; tests will be run unfiltered.\n"
        f"Your job is to propose isolation/security probes (tier: {tier}).\n\n"
        f"REPO TREE:\n{tree_str}\n\n"
        f"SOURCE EXCERPTS:\n{files_str}\n\n"
        f"OUTPUT FORMAT — strict YAML list of ProbeSpec objects:\n"
        f"```yaml\n"
        f"- name: <unique human-readable>\n"
        f"  pattern: api_read | api_list | api_modify | api_delete | ui_visibility | ui_invisibility | positive_control\n"
        f"  path: /api/path/here\n"
        f"  method: GET | POST | PUT | DELETE\n"
        f"  expected_status: 403   # or a list of acceptable codes\n"
        f"  soc2_controls: ['CC6.1', 'CC6.6']\n"
        f"  description: one-line human description\n"
        f"```\n\n"
        f"Return ONLY the YAML list. No commentary before or after."
    )


def _write_pytest_from_specs(repo_path: str, specs) -> Path:
    """Generate a pytest file inside the repo from a list of ProbeSpecs.

    Delegates to ProbeGenerator.generate_pytest_file — real ProbeRunner
    codegen, not pass-through assert True stubs. Without
    WORKFLO_API_BASE_URL (app-under-test not booted), the generated tests
    skip with an actionable reason rather than silently passing.
    """
    from probe_engine import ProbeConfig, ProbeGenerator

    repo = Path(repo_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir(exist_ok=True)
    pytest_file = tests_dir / "test_workflo_generated.py"

    config = ProbeConfig(
        name="workflo-model-generated",
        version="1.0",
        probes=list(specs),
        metadata={"source": "model_inference"},
    )
    pytest_file.write_text(ProbeGenerator.generate_pytest_file(config), encoding="utf-8")
    return pytest_file


def _run_canary_check(target_host: str = "https://example.com", timeout_seconds: float = 3.0) -> dict:
    """Attempt an outbound HTTPS request from inside the sandbox.

    The sandbox MUST be configured with --network none. If this request
    succeeds, isolation is broken and the receipt will document it.

    Returns a JSON-serializable dict matching CanaryCheckResult's shape.
    """
    import ssl
    import urllib.request
    import urllib.error
    import socket
    from datetime import datetime, UTC

    attempted_at = datetime.now(UTC).isoformat()
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(target_host, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ctx):
            return {
                "attempted_at": attempted_at,
                "target_host": target_host,
                "request_succeeded": True,
                "error": None,
            }
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return {
            "attempted_at": attempted_at,
            "target_host": target_host,
            "request_succeeded": False,
            "error": str(e),
        }
    except Exception as e:
        return {
            "attempted_at": attempted_at,
            "target_host": target_host,
            "request_succeeded": False,
            "error": f"unexpected: {type(e).__name__}: {e}",
        }


def _parse_results(results_path: Path) -> RunSummary:
    """Parse the pytest-json-report file into a RunSummary.

    Never raises: a missing, empty, or unparseable report file must not
    crash the worker (that swallows the honest collection error and turns
    into "exit 0, no report"). The caller's returncode-based
    collection_error logic then carries the real cause.
    """
    if not results_path.exists():
        return RunSummary()

    try:
        with open(results_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return RunSummary()

    summary_data = data.get("summary", {})
    return RunSummary(
        total=summary_data.get("total", 0),
        passed=summary_data.get("passed", 0),
        failed=summary_data.get("failed", 0),
        skipped=summary_data.get("skipped", 0),
        deselected=summary_data.get("deselected", 0),
        duration_seconds=data.get("duration", 0.0),
    )
