#!/usr/bin/env python3
"""Real llama.cpp smoke through the worker's active model-stage function.

The worker smoke exercises reasoning followed by test generation. A second
source-free request exercises the reporting adapter against synthetic structured
results. Reports contain only artifact identities and validation outcomes—never
source, prompts, generated tests, or narrative text.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from workflo_ai_integration import ModelRouter, ReportNarrative, RouterConfig
from workflo_worker.executor import _run_llamacpp_model_stage
from workflo_worker.model.llamacpp_runtime import (
    ADAPTER_NAMES,
    LlamaCppRuntime,
    LlamaCppRuntimeConfig,
)


class _Streamer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        # Keep logs local to this process. The JSON reports include only
        # source-free status/provenance.
        self.lines.append(str(message))


def _append_error(current: str | None, message: str) -> str:
    return f"{current}; {message}" if current else message


def _run_reporting_smoke() -> dict:
    """Run one real reporting request without retaining its input or output."""

    started_at = time.monotonic()
    inference_started: float | None = None
    config: LlamaCppRuntimeConfig | None = None
    runtime: LlamaCppRuntime | None = None
    router: ModelRouter | None = None
    error: str | None = None
    schema_valid = False
    requests = 0
    teardown_verified = False

    try:
        config = LlamaCppRuntimeConfig.from_env()
        runtime = LlamaCppRuntime(config)
        runtime.start()
        router = ModelRouter(
            RouterConfig(
                base_url=runtime.base_url,
                timeout_sec=config.request_timeout_seconds,
            )
        )
        discovered = router.discover_adapters()
        if set(discovered) != set(ADAPTER_NAMES):
            raise RuntimeError("reporting smoke did not discover the frozen adapter set")

        # Synthetic structured outcomes only. Neither this input nor the model's
        # narrative is written to logs or evidence.
        inference_started = time.monotonic()
        requests = 1
        narrative = router.generate_report(
            {
                "run_id": "gate4-reporting-smoke",
                "tests": {"total": 2, "passed": 2, "failed": 0},
                "findings": [],
            }
        )
        schema_valid = isinstance(narrative, ReportNarrative)
        if not schema_valid:
            raise RuntimeError("reporting adapter returned the wrong schema")
    except Exception as exc:  # report failure evidence instead of losing it
        error = f"{type(exc).__name__}: {exc}"[:1024]
    finally:
        if router is not None:
            try:
                router.close()
            except Exception as exc:
                error = _append_error(
                    error, f"router close failed ({type(exc).__name__})"
                )
        if runtime is not None:
            try:
                teardown_verified = runtime.stop()
            except Exception as exc:
                teardown_verified = False
                error = _append_error(
                    error, f"llama.cpp teardown failed ({type(exc).__name__})"
                )

    inference_seconds = (
        round(time.monotonic() - inference_started, 6)
        if inference_started is not None
        else 0.0
    )
    identity = {}
    if config is not None:
        identity = {
            "model": config.model_id,
            "server_image": config.image,
            "base_model_sha256": config.base_model.sha256,
            "adapter_sha256": {
                name: config.adapters[name].sha256 for name in ADAPTER_NAMES
            },
        }
    passed = bool(schema_valid and teardown_verified and not error and requests == 1)
    return {
        "passed": passed,
        "adapter": "reporting",
        "schema_valid": schema_valid,
        "requests": requests,
        "inference_seconds": inference_seconds,
        "elapsed_seconds": round(time.monotonic() - started_at, 6),
        "teardown_verified": teardown_verified,
        "endpoint_scope": "loopback",
        "input_scope": "synthetic-structured-results-only",
        "source_code_included": False,
        "narrative_recorded": False,
        "error": error,
        "identity": identity,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--reporting-out",
        type=Path,
        help="defaults to reporting-smoke.json next to --out",
    )
    args = parser.parse_args()
    reporting_out = args.reporting_out or args.out.with_name("reporting-smoke.json")

    with tempfile.TemporaryDirectory(prefix="workflo-real-model-smoke-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        (repo / "calculator.py").write_text(
            "def divide(total: int, count: int) -> float:\n"
            "    if count == 0:\n"
            "        raise ValueError('count must be non-zero')\n"
            "    return total / count\n",
            encoding="utf-8",
        )
        streamer = _Streamer()
        teardown, error, findings, generated_dir, provenance = _run_llamacpp_model_stage(
            streamer,
            str(repo),
            ["aggressive"],  # exercises reasoning followed by test-gen
        )

        generated_count = 0
        if generated_dir is not None and generated_dir.exists():
            generated_count = sum(1 for _ in generated_dir.rglob("test_*.py"))

        required_markers = {
            "artifacts_verified_and_server_started": any(
                "verifying pinned GGUF artifacts" in line for line in streamer.lines
            ),
            "all_adapters_discovered": any(
                "discovered required llama.cpp adapters" in line for line in streamer.lines
            ),
            "validated_test_written": any(
                "wrote validated llama.cpp pytest file" in line for line in streamer.lines
            ),
        }
        worker_passed = bool(
            teardown
            and not error
            and findings
            and generated_count
            and provenance
            and all(required_markers.values())
        )

    reporting_report = _run_reporting_smoke()
    report = {
        "passed": bool(worker_passed and reporting_report["passed"]),
        "worker_passed": worker_passed,
        "reporting_passed": reporting_report["passed"],
        "reporting_report": reporting_out.name,
        "teardown_verified": teardown,
        "error": error,
        "findings_count": len(findings),
        "generated_tests_count": generated_count,
        "provenance": provenance,
        "required_log_markers": required_markers,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    reporting_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    reporting_out.write_text(
        json.dumps(reporting_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not report["passed"]:
        print(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps(reporting_report, indent=2, sort_keys=True))
        return 1
    print(
        "real llama.cpp worker + reporting smoke passed; "
        f"worker_report={args.out}; reporting_report={reporting_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
