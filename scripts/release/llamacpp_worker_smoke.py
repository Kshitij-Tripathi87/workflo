#!/usr/bin/env python3
"""Real llama.cpp smoke through the worker's active model-stage function.

This is intentionally not mockable from the workflow: it requires the pinned
binary/image identity, base GGUF, and all three adapter files. It records only
artifact identities and validation outcomes—never the synthetic source or
model-generated test content.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from workflo_worker.executor import _run_llamacpp_model_stage


class _Streamer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        # Keep logs local to this process. The JSON report below includes only
        # source-free status/provenance.
        self.lines.append(str(message))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

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

        generated = []
        if generated_dir is not None and generated_dir.exists():
            generated = [str(path.relative_to(repo)) for path in generated_dir.rglob("test_*.py")]

        report = {
            "passed": bool(teardown and not error and findings and generated and provenance),
            "teardown_verified": teardown,
            "error": error,
            "findings_count": len(findings),
            "generated_tests_count": len(generated),
            "provenance": provenance,
            "required_log_markers": {
                "artifacts_verified_and_server_started": any(
                    "verifying pinned GGUF artifacts" in line for line in streamer.lines
                ),
                "all_adapters_discovered": any(
                    "discovered required llama.cpp adapters" in line for line in streamer.lines
                ),
                "validated_test_written": any(
                    "wrote validated llama.cpp pytest file" in line for line in streamer.lines
                ),
            },
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["passed"] or not all(report["required_log_markers"].values()):
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    print(f"real llama.cpp worker smoke passed; report={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
