"""Fail-closed registry for the frozen GGUF artifact manifest.

Loads ``serving/model-artifacts.json``, verifies the SHA-256 digest of every
referenced file on disk, and exposes an immutable metadata snapshot that the
HTTP service attaches to every response and log line.

Design rules (mirroring the rest of the fail-closed serving contract):

  - Construction fails on ANY structural mismatch, unknown adapter name,
    missing file, or digest mismatch. A tampered or incomplete artifact set
    must prevent the service from starting, not degrade at request time.
  - The registry never reads model weights or returns file contents. It only
    exposes identities (paths, digests, sources) — safe for telemetry.
  - Digests are computed at startup and cached. Re-verification after a
    suspected swap is an explicit ``reverify()`` call, so hot-loop request
    handling never pays for hashing 2.5 GB base weights.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_ADAPTERS = ("test-gen", "reasoning", "reporting")
MANIFEST_VERSION = 1
_CHUNK_SIZE = 1024 * 1024

# Environment override for the manifest location, so deployment layouts do
# not have to mirror the repository tree.
MANIFEST_ENV_VAR = "WORKFLO_ARTIFACT_MANIFEST"


class ArtifactRegistryError(RuntimeError):
    """Raised when the artifact manifest is missing, malformed, or tampered."""


def default_manifest_path() -> Path:
    """Resolve the manifest path from the environment or the repo layout."""
    override = os.environ.get(MANIFEST_ENV_VAR)
    if override:
        return Path(override)
    # src/workflo_ai_integration/artifact_registry.py -> package root/serving
    package_root = Path(__file__).resolve().parents[2]
    return package_root / "serving" / "model-artifacts.json"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactRegistryError(f"cannot read artifact file {path}: {exc}") from exc
    return digest.hexdigest()


@dataclass(frozen=True)
class AdapterIdentity:
    task: str
    path: str
    sha256: str
    source: str


@dataclass(frozen=True)
class ArtifactSnapshot:
    """Immutable identity metadata — safe to embed in responses and logs."""

    llama_cpp_image: str
    model_id: str
    model_path: str
    model_sha256: str
    model_source: str
    adapters: dict[str, AdapterIdentity]

    def to_dict(self) -> dict[str, Any]:
        return {
            "llama_cpp_image": self.llama_cpp_image,
            "model": {
                "id": self.model_id,
                "path": self.model_path,
                "sha256": self.model_sha256,
            },
            "adapters": {
                task: {"path": a.path, "sha256": a.sha256}
                for task, a in sorted(self.adapters.items())
            },
        }


class ArtifactRegistry:
    """Loads, verifies, and serves the frozen artifact manifest."""

    def __init__(self, manifest_path: Path | None = None, verify_files: bool = True):
        self.manifest_path = (manifest_path or default_manifest_path()).resolve()
        self._snapshot: ArtifactSnapshot | None = None
        self._artifact_dir = self.manifest_path.parent
        self._document: dict[str, Any] = self._load_document()
        self._snapshot = self._build_snapshot()
        if verify_files:
            self.reverify()

    # -- loading -----------------------------------------------------------

    def _load_document(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            raise ArtifactRegistryError(
                f"artifact manifest not found: {self.manifest_path}"
            )
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ArtifactRegistryError(
                f"artifact manifest is not valid JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ArtifactRegistryError("artifact manifest must be a JSON object")
        if raw.get("version") != MANIFEST_VERSION:
            raise ArtifactRegistryError(
                f"artifact manifest version must be {MANIFEST_VERSION}, "
                f"got {raw.get('version')!r}"
            )
        image = raw.get("llama_cpp_image")
        if not isinstance(image, str) or not image.startswith("ghcr.io/"):
            raise ArtifactRegistryError("llama_cpp_image must be a pinned ghcr.io digest")
        if "@sha256:" not in image:
            raise ArtifactRegistryError("llama_cpp_image must be pinned by sha256 digest")
        model = raw.get("model")
        if not isinstance(model, dict):
            raise ArtifactRegistryError("artifact manifest is missing the model block")
        adapters = raw.get("adapters")
        if not isinstance(adapters, dict):
            raise ArtifactRegistryError("artifact manifest is missing the adapters block")
        missing = [t for t in REQUIRED_ADAPTERS if t not in adapters]
        extra = [t for t in adapters if t not in REQUIRED_ADAPTERS]
        if missing or extra:
            raise ArtifactRegistryError(
                f"adapters must be exactly {REQUIRED_ADAPTERS}; "
                f"missing={missing}, unexpected={extra}"
            )
        return raw

    @staticmethod
    def _require_str(block: dict[str, Any], key: str, label: str) -> str:
        value = block.get(key)
        if not isinstance(value, str) or not value:
            raise ArtifactRegistryError(f"{label}.{key} must be a non-empty string")
        return value

    def _resolve_artifact_path(self, rel_path: str, label: str) -> Path:
        candidate = (self._artifact_dir / rel_path).resolve()
        # Containment: an absolute or traversing manifest path must never
        # point outside the serving/ directory.
        try:
            candidate.relative_to(self._artifact_dir)
        except ValueError as exc:
            raise ArtifactRegistryError(
                f"{label} path '{rel_path}' escapes the serving directory"
            ) from exc
        return candidate

    def _parse_artifact_block(
        self, block: Any, label: str
    ) -> tuple[str, str, str, Path]:
        """Validate one {path, sha256, source} block; return (path, sha, source, resolved)."""
        if not isinstance(block, dict):
            raise ArtifactRegistryError(f"{label} must be an object")
        rel_path = self._require_str(block, "path", label)
        sha = self._require_str(block, "sha256", label)
        source = self._require_str(block, "source", label)
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ArtifactRegistryError(
                f"{label}.sha256 must be a 64-char lowercase hex digest"
            )
        if not rel_path.endswith(".gguf"):
            raise ArtifactRegistryError(f"{label}.path must reference a .gguf file")
        resolved = self._resolve_artifact_path(rel_path, label)
        return rel_path, sha, source, resolved

    def _build_snapshot(self) -> ArtifactSnapshot:
        model_id = self._require_str(self._document["model"], "id", "model")
        model_path, model_sha, model_source, _ = self._parse_artifact_block(
            self._document["model"], "model"
        )
        adapters: dict[str, AdapterIdentity] = {}
        for task in REQUIRED_ADAPTERS:
            rel_path, sha, source, _ = self._parse_artifact_block(
                self._document["adapters"][task], f"adapters.{task}"
            )
            adapters[task] = AdapterIdentity(
                task=task, path=rel_path, sha256=sha, source=source
            )
        return ArtifactSnapshot(
            llama_cpp_image=self._document["llama_cpp_image"],
            model_id=model_id,
            model_path=model_path,
            model_sha256=model_sha,
            model_source=model_source,
            adapters=adapters,
        )

    # -- verification --------------------------------------------------------

    def reverify(self) -> ArtifactSnapshot:
        """Re-hash every artifact on disk and compare against the manifest.

        Fail-closed: any missing file or digest mismatch raises
        ArtifactRegistryError and leaves the previously verified snapshot
        intact for callers that only need identity metadata.
        """
        assert self._snapshot is not None
        _, expected_sha, _, model_path = self._parse_artifact_block(
            self._document["model"], "model"
        )
        self._check_digest(model_path, expected_sha, "model")
        for task in REQUIRED_ADAPTERS:
            block = self._document["adapters"][task]
            _, expected_sha, _, adapter_path = self._parse_artifact_block(
                block, f"adapters.{task}"
            )
            self._check_digest(adapter_path, expected_sha, f"adapter {task}")
        return self._snapshot

    @staticmethod
    def _check_digest(path: Path, expected: str, label: str) -> None:
        if not path.is_file():
            raise ArtifactRegistryError(f"{label} artifact file is missing: {path}")
        actual = _sha256_of(path)
        if actual != expected:
            raise ArtifactRegistryError(
                f"{label} artifact digest mismatch for {path.name}: "
                f"manifest={expected} disk={actual}"
            )

    # -- accessors -----------------------------------------------------------

    @property
    def snapshot(self) -> ArtifactSnapshot:
        assert self._snapshot is not None
        return self._snapshot

    def telemetry(self) -> dict[str, Any]:
        """Metadata payload for request logs and API responses."""
        return self.snapshot.to_dict()
