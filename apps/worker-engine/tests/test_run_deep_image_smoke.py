from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "run_deep_image_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_deep_image_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deep_smoke_records_isolation_and_explicit_removal(monkeypatch, tmp_path):
    module = _load_module()
    image = "registry.example/deep@sha256:" + "a" * 64
    output = tmp_path / "evidence"
    isolation = output / "container-isolation.json"
    state = {"created": False}

    def completed(returncode=0, stdout=""):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    def fake_call(command, *, check=True):
        if command[:2] == ["docker", "run"]:
            return completed()
        if command[:3] == ["docker", "rm", "-f"]:
            state["created"] = False
            return completed()
        if command[:2] == ["docker", "create"]:
            state["created"] = True
            return completed(stdout="container-id")
        if command[:2] == ["docker", "inspect"]:
            if not state["created"]:
                return completed(returncode=1)
            return completed(stdout=json.dumps([{"HostConfig": {
                "NetworkMode": "none",
                "PortBindings": {},
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
            }}]))
        if command[:3] == ["docker", "start", "--attach"]:
            output.mkdir(parents=True, exist_ok=True)
            (output / "llamacpp-worker-smoke.json").write_text(
                json.dumps({"passed": True})
            )
            (output / "reporting-smoke.json").write_text(
                json.dumps({"passed": True})
            )
            return completed()
        raise AssertionError(command)

    monkeypatch.setattr(module, "_call", fake_call)
    monkeypatch.setattr(sys, "argv", [
        str(SCRIPT), "--image", image, "--out-dir", str(output),
        "--name", "candidate", "--isolation-report", str(isolation),
    ])

    assert module.main() == 0
    report = json.loads(isolation.read_text())
    assert report["passed"] is True
    assert report["network_none"] is True
    assert report["no_published_ports"] is True
    assert report["no_ollama"] is True
    assert report["container_removed"] is True
