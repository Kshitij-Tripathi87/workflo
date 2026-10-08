"""Worker main loop — polls the queue for run specs and executes them.

In Phase 1, used standalone inside a sandbox container with:
    python -m workflo_worker --spec-file /workspace/spec.json --repo-path /workspace/repo

The worker reads the spec, runs pytest in the repo path, runs the canary
check, and emits:
    - WORKFLO_REPORT: {json}  — the RunSummary for the executor to parse
    - WORKFLO_CANARY:  {json} — the canary result for the executor to parse
"""

import argparse
import json
import os
import sys

from workflo_utils.logging import configure_logging, get_logger

from workflo_worker.executor import execute_run
from workflo_worker.streamer import ResultStreamer

logger = get_logger(__name__)


def run_worker():
    """Main worker entrypoint.

    Supports two modes:
    1. CLI: `python -m workflo_worker --spec-file <path> [--repo-path <path>]`
    2. Idle:  no args — waits for the queue (Phase 2 work)
    """
    configure_logging()

    parser = argparse.ArgumentParser(description="workflo worker")
    parser.add_argument("--spec-file", help="Path to JSON spec file (e.g., /workspace/spec.json)")
    parser.add_argument("--repo-path", default="/workspace/repo",
                        help="Path inside this container where the repo was mounted")
    # Legacy arg kept for backward compatibility with old callers (if any)
    parser.add_argument("positional_spec", nargs="?",
                        help="Legacy: path to spec file as positional argument")
    args = parser.parse_args()

    spec_file = args.spec_file or args.positional_spec

    if spec_file:
        # Forward the repo path to the executor via env var (executor reads it).
        os.environ["WORKFLO_REPO_PATH"] = args.repo_path
        logger.info("worker.start", extra={"extra_data": {"spec_file": spec_file, "repo_path": args.repo_path}})

        try:
            with open(spec_file) as f:
                full_spec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            err_report = json.dumps({"run_id": None, "total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_seconds": 0, "soc2_controls_covered": [], "findings": []})
            print("WORKFLO_REPORT: " + err_report, flush=True)
            print(f"WORKFLO_ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            sys.exit(2)

        # The spec file is a SandboxSpec — the executor's full JSON. But
        # the worker's run() function needs just the RunSpec portion
        # (goal, markers, env, targets, config, artifacts). Extract it.
        # If the spec is already a RunSpec-shaped dict (no `run_spec` key),
        # use it as-is (legacy callers / future direct invocations).
        if isinstance(full_spec, dict) and "run_spec" in full_spec and isinstance(full_spec["run_spec"], dict):
            spec = full_spec["run_spec"]
            # Carry through a few useful top-level fields if present.
            if "sandbox_id" in full_spec:
                spec.setdefault("sandbox_id", full_spec["sandbox_id"])
            if "commit_sha" in full_spec and full_spec["commit_sha"]:
                spec["commit_sha"] = full_spec["commit_sha"]
            if "repo_url" in full_spec and full_spec["repo_url"]:
                spec["repo_url"] = full_spec["repo_url"]
        else:
            spec = full_spec
        _process(spec)
    else:
        logger.info("No spec provided. Running in idle mode (waiting for queue).")
        _idle_loop()


def _process(spec: dict):
    run_id = spec.get("run_id") or spec.get("sandbox_id") or "local"
    logger.info("run.received", extra={"extra_data": {"run_id": run_id, "goal": spec.get("goal")}})
    streamer = ResultStreamer(run_id=run_id)
    try:
        summary = execute_run(spec, streamer)
        streamer.complete(summary)
        logger.info("run.completed", extra={"extra_data": {"run_id": run_id, "summary": summary.model_dump()}})
    except Exception as e:
        logger.error("run.failed", extra={"extra_data": {"run_id": run_id, "error": str(e)}})
        streamer.fail(str(e))


def _idle_loop():
    import time
    while True:
        time.sleep(5)
        logger.info("worker.heartbeat")


if __name__ == "__main__":
    run_worker()
