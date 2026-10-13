"""Shared deterministic fakes for HTTP service tests (no GPU, no llama-server)."""

import hashlib
import json
import tempfile
from pathlib import Path

from workflo_ai_integration.artifact_registry import ArtifactRegistry
from workflo_ai_integration.schemas import (
    ProposeInvariantCall,
    ReportNarrative,
    WriteTestCall,
)


class FakeRouter:
    """Mirrors the ModelRouter surface used by service.py, fully offline."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def discover_adapters(self, force: bool = False) -> dict[str, int]:
        return {"test-gen": 0, "reasoning": 1, "reporting": 2}

    def generate_for_task(self, task: str, system_prompt: str, user_prompt: str):
        self.calls.append((task, system_prompt, user_prompt))
        if task == "test-gen":
            return WriteTestCall(
                path="workflo_generated_tests/test_fake.py",
                content="def test_fake():\n    assert True\n",
                rationale="deterministic fixture output",
            )
        if task == "reasoning":
            return ProposeInvariantCall(
                description="fixture invariant",
                target="app.x",
                category="business_logic",
                hypothesis_strategy="st.integers(min_value=0)",
                property_check="f(x) >= 0",
            )
        raise ValueError(f"unknown task '{task}'")

    def generate_report(self, results_json: dict) -> ReportNarrative:
        self.calls.append(("reporting", "", json.dumps(results_json)))
        return ReportNarrative(
            summary="97 passed, 3 failed in billing.",
            findings=[],
            priority_order=[],
        )


def build_fake_registry(tmp_path: Path | None = None) -> ArtifactRegistry:
    """A tiny but fully verified artifact set (fake bytes, real digests)."""
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="workflo-serving-test-"))
    serving = tmp_path / "serving-fake"
    (serving / "models").mkdir(parents=True, exist_ok=True)
    (serving / "adapters").mkdir(parents=True, exist_ok=True)

    def write(rel: str) -> str:
        payload = f"GGUF-fake::{rel}".encode()
        (serving / rel).write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    manifest = serving / "model-artifacts.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "llama_cpp_image": "ghcr.io/ggml-org/llama.cpp:server@sha256:" + "b" * 64,
                "model": {
                    "id": "fake-base",
                    "source": "hf:fake/base",
                    "path": "models/base.gguf",
                    "sha256": write("models/base.gguf"),
                },
                "adapters": {
                    task: {
                        "source": "fake",
                        "path": f"adapters/{task}.gguf",
                        "sha256": write(f"adapters/{task}.gguf"),
                    }
                    for task in ("test-gen", "reasoning", "reporting")
                },
            }
        ),
        encoding="utf-8",
    )
    return ArtifactRegistry(manifest_path=manifest)
