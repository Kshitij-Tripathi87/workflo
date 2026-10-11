"""Test executor — runs pytest with the spec's markers and collects results.

Reads PROBE_GROUPS environment variable to determine which probe groups
to execute. Probe groups are composable: ["surface", "security"] etc.

For deep-test / aggressive-test tiers, this also:
  - Verifies pinned GGUF base/adapter hashes and starts local llama.cpp
  - Feeds a budgeted repo snapshot only to that loopback process
  - Routes through task-specific adapters with strict schemas and compile gates
  - Runs the validated generated pytest alongside surface tests
  - Stops the server and verifies ephemeral state removal

The model stage is gated behind the flag — plain --test / --security never
boots llama.cpp. This keeps the base image small, fast, and free of model weights
for the 90% of runs that don't need them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Optional

from workflo_ai_integration import (
    AdapterLoadError,
    GenerationValidationError,
    ModelRouter,
    ProposeInvariantCall,
    RouterConfig,
    WriteTestCall,
)
from workflo_schema import RunSpec, RunSummary

from workflo_worker.model import (
    LlamaCppRuntime,
    LlamaCppRuntimeConfig,
    LlamaCppRuntimeError,
    ModelOutputInvalid,
    ModelServer,
    ModelServerConfig,
    ModelServerError,
    build_correction_prompt,
    generate_from_model_output,
    wipe_model_state,
)
from workflo_worker.security.stage import run_security_stage
from workflo_worker.streamer import ResultStreamer
from workflo_worker.web.stage import run_web_stage

# Repo file tree budget — how many source lines enter local inference. The
# release runtime has a separately configured context limit; keep deterministic
# headroom for system instructions, structured output, and corrections.
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

    streamer.log("Executing pytest with markers: (none — surface tier runs all tests)")
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
    model_provenance: Optional[dict] = None
    needs_model_stage = bool(set(probe_groups) & {"deep", "aggressive"})

    if needs_model_stage:
        (
            model_inference_teardown,
            model_inference_error,
            model_findings,
            model_generated_tests_dir,
            model_provenance,
        ) = _run_model_stage(streamer, repo_path, probe_groups)
        # Persist model stage status to the host-side executor. Both records are
        # parsed into signed receipt fields; neither contains generated source.
        model_status = {
            "teardown": model_inference_teardown,
            "error": model_inference_error,
            "findings_count": len(model_findings),
        }
        streamer.log(f"WORKFLO_MODEL_TEARDOWN: {json.dumps(model_status)}")
        if model_provenance is not None:
            streamer.log(f"WORKFLO_LOCAL_MODEL_PROVENANCE: {json.dumps(model_provenance)}")

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

    # A requested model tier must never silently degrade to surface tests.
    # Record the model failure as a collection error so the host marks the run
    # failed while still producing a signed diagnostic receipt.
    if needs_model_stage and model_inference_error:
        summary.collection_error = f"model stage failed: {model_inference_error}"

    # Honest collection accounting: pytest exits 1 when tests FAIL (a valid
    # outcome), but exits >=2 on collection/internal errors, or nonzero with
    # nothing collected. In both latter cases the repo's tests never really
    # ran — say so instead of reporting a clean 0/0.
    pytest_error: Optional[str] = None
    if proc is not None and proc.returncode >= 2:
        pytest_error = f"pytest exited {proc.returncode} (collection/internal error)"
    elif proc is not None and proc.returncode != 0 and summary.total == 0:
        pytest_error = f"pytest exited {proc.returncode} with 0 tests collected"
    if pytest_error:
        summary.collection_error = (
            f"{summary.collection_error}; {pytest_error}"
            if summary.collection_error
            else pytest_error
        )
    if summary.collection_error and install_error:
        summary.collection_error += f"; offline repo install failed: {install_error}"
    elif summary.collection_error and proc is not None and proc.stderr:
        summary.collection_error += f"; stderr: {proc.stderr[-300:].strip()}"

    # Merge only the source-free model validation marker into the report.
    # Model-authored text and generated code remain in the ephemeral repo;
    # surface pytest results stay in the summary.
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
) -> tuple[Optional[bool], Optional[str], list[dict], Optional[Path], Optional[dict]]:
    """Select the release model backend; llama.cpp is the fail-closed default."""
    backend = (os.environ.get("WORKFLO_MODEL_BACKEND") or "llamacpp").strip().lower()
    if backend == "llamacpp":
        return _run_llamacpp_model_stage(streamer, repo_path, probe_groups)
    if backend == "ollama":
        # Temporary compatibility path for pre-release images. The release
        # image sets llama.cpp explicitly; unsupported values never fall back.
        teardown, error, findings, generated = _run_ollama_model_stage(
            streamer, repo_path, probe_groups
        )
        return teardown, error, findings, generated, None
    return False, f"unsupported model backend: {backend}", [], None, None


def _run_llamacpp_model_stage(
    streamer: ResultStreamer,
    repo_path: str,
    probe_groups: list[str],
) -> tuple[bool, Optional[str], list[dict], Optional[Path], Optional[dict]]:
    """Run the pinned local llama.cpp router and produce executable pytest.

    The runtime owns the server process and binds it to loopback. The router
    validates adapter discovery, schema output, safe paths, and generated code
    before this function writes anything into the disposable repository copy.
    """
    findings: list[dict] = []
    generated_tests_dir: Optional[Path] = None
    provenance: Optional[dict] = None
    router: Optional[ModelRouter] = None
    runtime: Optional[LlamaCppRuntime] = None
    requests = 0
    started_at = time.monotonic()
    error: Optional[str] = None

    try:
        config = LlamaCppRuntimeConfig.from_env()
        runtime = LlamaCppRuntime(config)
        streamer.log("[model] verifying pinned GGUF artifacts and starting llama.cpp...")
        runtime.start()
        provenance = runtime.provenance()
        router = ModelRouter(
            RouterConfig(
                base_url=runtime.base_url,
                timeout_sec=config.request_timeout_seconds,
            )
        )
        adapters = router.discover_adapters()
        streamer.log(f"[model] discovered required llama.cpp adapters: {sorted(adapters)}")

        repo_prompt = _build_repo_analysis_prompt(repo_path, probe_groups)
        streamer.log(f"[model] local source prompt built ({len(repo_prompt)} chars)")
        system_prompt = (
            "Generate a single deterministic pytest file for the repository snapshot. "
            "Return only the required JSON object. Do not use network, subprocess, "
            "filesystem mutation, dynamic execution, or paths outside the generated-test directory."
        )

        def generate(flag: str, prompt: str):
            nonlocal requests
            last_error: Optional[Exception] = None
            for attempt in range(2):
                requests += 1
                try:
                    return router.generate_for_flag(flag, system_prompt, prompt)
                except GenerationValidationError as exc:
                    last_error = exc
                    streamer.log(
                        f"[model] validated generation attempt {attempt + 1} failed: {exc}"
                    )
                    prompt += (
                        "\n\nThe prior response failed strict validation. Return a corrected JSON "
                        "object matching the requested schema; include no commentary."
                    )
            raise GenerationValidationError(
                f"model output invalid after one retry: {last_error}"
            )

        invariant: Optional[ProposeInvariantCall] = None
        if "aggressive" in probe_groups:
            invariant_obj = generate("--aggressive-test", repo_prompt)
            if not isinstance(invariant_obj, ProposeInvariantCall):
                raise GenerationValidationError("reasoning adapter returned the wrong schema")
            invariant = invariant_obj
            test_prompt = (
                f"{repo_prompt}\n\nValidated invariant to exercise:\n"
                f"description={invariant.description}\n"
                f"target={invariant.target}\n"
                f"strategy={invariant.hypothesis_strategy}\n"
                f"property={invariant.property_check}\n"
            )
        else:
            test_prompt = repo_prompt

        generated = generate("--deep-test", test_prompt)
        if not isinstance(generated, WriteTestCall):
            raise GenerationValidationError("test-generation adapter returned the wrong schema")
        pytest_file = _write_llamacpp_test(repo_path, generated)
        generated_tests_dir = pytest_file.parent
        streamer.log("[model] wrote validated llama.cpp pytest file")

        # Never project model-authored rationale, invariant text, source, or
        # generated code into receipts/log artifacts: those may reproduce
        # repository content. Record only bounded identities and validation
        # outcomes; executable content remains in the ephemeral repo copy.
        finding = {
            "name": "validated-local-model-test",
            "path": "workflo_generated_tests/[redacted]",
            "description": "validated local-model pytest file generated",
            "source": "llamacpp_test_gen_adapter",
            "model": config.model_id,
            "base_model_sha256": config.base_model.sha256,
        }
        if invariant is not None:
            finding["invariant_category"] = invariant.category
        findings.append(finding)
    except (AdapterLoadError, GenerationValidationError, LlamaCppRuntimeError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        streamer.log(f"[model] ERROR: {error}")
    finally:
        if router is not None:
            router.close()
        teardown_ok = False
        if runtime is not None:
            try:
                teardown_ok = runtime.stop()
            except OSError as exc:
                teardown_ok = False
                teardown_error = f"llama.cpp teardown failed: {type(exc).__name__}: {exc}"
                error = f"{error}; {teardown_error}" if error else teardown_error
        if provenance is not None:
            provenance.update(
                {
                    "requests": requests,
                    "inference_seconds": round(time.monotonic() - started_at, 6),
                    "error": error,
                }
            )

    if not teardown_ok:
        teardown_error = "llama.cpp process or ephemeral state was not verified gone"
        error = f"{error}; {teardown_error}" if error else teardown_error
    return teardown_ok, error, findings, generated_tests_dir, provenance


def _write_llamacpp_test(repo_path: str, generated: WriteTestCall) -> Path:
    """Write beneath a dedicated directory, with a second containment check."""
    repo = Path(repo_path).resolve(strict=True)
    root = (repo / "workflo_generated_tests").resolve()
    relative = PurePosixPath(generated.path)
    destination = root.joinpath(*relative.parts).resolve()
    if not destination.is_relative_to(root):
        raise GenerationValidationError("generated test destination escaped its root")
    if destination.exists():
        raise GenerationValidationError("generated test destination already exists")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_text(generated.content, encoding="utf-8")
    except OSError as exc:
        # Do not include the model-authored path or generated content in logs
        # or signed provenance.
        raise GenerationValidationError(
            f"generated test write failed ({type(exc).__name__}, errno={exc.errno})"
        ) from exc
    return destination


def _run_ollama_model_stage(
    streamer: ResultStreamer,
    repo_path: str,
    probe_groups: list[str],
) -> tuple[Optional[bool], Optional[str], list[dict], Optional[Path]]:
    """Legacy Ollama implementation retained only for migration compatibility."""
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
    import socket
    import ssl
    import urllib.error
    import urllib.request
    from datetime import UTC, datetime

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
