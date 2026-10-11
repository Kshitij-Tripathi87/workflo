#!/usr/bin/env python3
"""Run worker/reporting smoke in an immutable, networkless deep image."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PINNED_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _call(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--isolation-report", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "passed": False,
        "network_none": False,
        "no_published_ports": False,
        "read_only": False,
        "capabilities_dropped": False,
        "no_ollama": False,
        "container_removed": False,
        "failure_class": None,
    }
    created = False
    try:
        if not PINNED_IMAGE.fullmatch(args.image):
            raise ValueError("deep image must be digest-pinned")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        output = args.out_dir.resolve()

        ollama = _call(
            [
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--entrypoint", "/bin/sh", args.image, "-c",
                "! command -v ollama >/dev/null 2>&1",
            ],
            check=False,
        )
        report["no_ollama"] = ollama.returncode == 0
        if not report["no_ollama"]:
            raise ValueError("Ollama executable exists in the release image")

        _call(["docker", "rm", "-f", args.name], check=False)
        _call(
            [
                "docker", "create", "--name", args.name,
                "--network", "none", "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=1g",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--pids-limit", "512", "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,src={output},dst=/evidence",
                "--entrypoint", "python", args.image,
                "/app/scripts/release/llamacpp_worker_smoke.py",
                "--out", "/evidence/llamacpp-worker-smoke.json",
                "--reporting-out", "/evidence/reporting-smoke.json",
            ]
        )
        created = True
        inspection = json.loads(_call(["docker", "inspect", args.name]).stdout)[0]
        host = inspection.get("HostConfig", {})
        report["network_none"] = host.get("NetworkMode") == "none"
        report["no_published_ports"] = not bool(host.get("PortBindings"))
        report["read_only"] = host.get("ReadonlyRootfs") is True
        report["capabilities_dropped"] = "ALL" in (host.get("CapDrop") or [])
        if not all(
            report[field]
            for field in (
                "network_none", "no_published_ports", "read_only", "capabilities_dropped"
            )
        ):
            raise ValueError("deep smoke container isolation configuration is unsafe")

        smoke = _call(["docker", "start", "--attach", args.name], check=False)
        if smoke.returncode != 0:
            # The harness itself writes redacted partial reports. Do not echo
            # container output, which is not required evidence.
            raise RuntimeError("deep image smoke returned non-zero")
        worker = json.loads((output / "llamacpp-worker-smoke.json").read_text())
        reporting = json.loads((output / "reporting-smoke.json").read_text())
        if worker.get("passed") is not True or reporting.get("passed") is not True:
            raise RuntimeError("deep image smoke evidence did not pass")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        report["failure_class"] = type(exc).__name__
    finally:
        if created:
            _call(["docker", "rm", "-f", args.name], check=False)
        absent = _call(["docker", "inspect", args.name], check=False).returncode != 0
        report["container_removed"] = absent

    report["passed"] = bool(
        report["network_none"]
        and report["no_published_ports"]
        and report["read_only"]
        and report["capabilities_dropped"]
        and report["no_ollama"]
        and report["container_removed"]
        and report["failure_class"] is None
    )
    _write(args.isolation_report, report)
    if not report["passed"]:
        print(
            f"deep image smoke failed ({report['failure_class'] or 'unknown_failure'})",
            file=sys.stderr,
        )
        return 1
    print("deep image worker/reporting smoke passed with explicit teardown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
