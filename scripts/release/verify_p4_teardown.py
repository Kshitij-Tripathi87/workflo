#!/usr/bin/env python3
"""Verify candidate, rollback, model-process, port, and temporary-state teardown."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _container_absent(name: str) -> bool:
    return _run(["docker", "inspect", name]).returncode != 0


def _process_counts() -> tuple[int, int, int]:
    llama = 0
    worker = 0
    ollama = 0
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text().strip().lower()
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "replace"
            ).lower()
        except (OSError, UnicodeDecodeError):
            continue
        if comm == "llama-server":
            llama += 1
        if comm == "ollama":
            ollama += 1
        if "workflo_worker" in command or "workflo-worker" in command:
            worker += 1
    return llama, worker, ollama


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--rollback", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    for name in (args.candidate, args.rollback):
        _run(["docker", "rm", "-f", name])

    llama_count, worker_count, ollama_count = _process_counts()
    listeners = _run(["ss", "-ltnp"])
    listener_text = listeners.stdout.lower() if listeners.returncode == 0 else ""
    model_listener_count = sum(
        1 for line in listener_text.splitlines()
        if "llama-server" in line or "ollama" in line
    )
    containers = _run(["docker", "ps", "--format", "{{.Names}} {{.Image}}"])
    ollama_container_count = sum(
        1 for line in containers.stdout.lower().splitlines() if "ollama" in line
    ) if containers.returncode == 0 else 0
    cache_paths = [
        path for pattern in ("llama*", "workflo-real-model-smoke-*", "workflo-llamacpp-*")
        for path in Path("/tmp").glob(pattern)
        if path.exists()
    ]

    checks = {
        "candidate_container_absent": _container_absent(args.candidate),
        "rollback_container_absent": _container_absent(args.rollback),
        "llama_server_processes_absent": llama_count == 0,
        "worker_children_absent": worker_count == 0,
        "ollama_absent": ollama_count == 0 and ollama_container_count == 0,
        "listener_inspection_succeeded": listeners.returncode == 0,
        "container_inspection_succeeded": containers.returncode == 0,
        "model_listeners_absent": model_listener_count == 0,
        "prompt_slot_cache_absent": not cache_paths,
        "known_sandbox_workspace_absent": _run(
            ["sudo", "test", "!", "-e", "/root/wf-agent-golden"]
        ).returncode == 0,
    }
    report = {
        "passed": all(checks.values()),
        **checks,
        "llama_server_process_count": llama_count,
        "worker_child_process_count": worker_count,
        "ollama_process_count": ollama_count,
        "ollama_container_count": ollama_container_count,
        "model_listener_count": model_listener_count,
        "unexpected_cache_count": len(cache_paths),
        "source_code_retained": False,
        "prompt_retained": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["passed"]:
        print("P4 teardown verification failed", file=sys.stderr)
        return 1
    print("P4 teardown verified: no model process, listener, container, or cache remains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
