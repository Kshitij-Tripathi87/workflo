"""Internal profile shared by the local dev producer and offline verifier.

There is only one admission policy here, not a user-editable policy language.
None of these profile rules admit a hosted, agent or production run.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workflo_schema.contracts import (
    CapabilityId,
    ExecutionPolicyBundleV1,
    PolicyComponentId,
    PolicyComponentV1,
    RetentionClass,
    RetentionSpecV1,
    RunCreatorV1,
    is_safe_relative_path,
)
from workflo_schema.contracts.canonical import digest_of
from workflo_schema.contracts.common import DigestString

PROFILE_ID = "local-pytest-dev-v1"
MAX_SOURCE_FILES = 512
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CHECKS = 256
RESOURCE_LIMITS = {"memory_mb": 512, "cpu_cores": 1, "pids_max": 64, "timeout_seconds": 60}
CAPABILITIES = (
    CapabilityId.SOURCE_ACQUIRE,
    CapabilityId.TESTS_EXECUTE,
    CapabilityId.EVIDENCE_SUBMIT,
)
RETENTION = RetentionSpecV1(
    retention_policy_id="local-manual",
    logs=RetentionClass.EPHEMERAL,
    artifacts=RetentionClass.CONTRACTUAL,
    receipts=RetentionClass.CONTRACTUAL,
)
LANDLOCK_RULES = (
    ("/", "read"),
    ("/tmp", "rw"),
    ("/home/workflo", "rw"),
    ("/workflo/artifacts", "rw"),
    ("/dev/null", "rw"),
)
TEST_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/home/workflo",
    "PYTHONPATH": "/opt/workflo/site",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
}


def validate_revision(commit: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("a full lowercase Git SHA-1 commit is required (no refs or abbreviations)")
    return commit


def validate_source_path(path: str) -> str:
    if not is_safe_relative_path(path) or ".git" in path.lower().split("/"):
        raise ValueError("expected a normalized repository-relative path without .git")
    return path


def pytest_argv(test_file: str) -> list[str]:
    if not validate_source_path(test_file).endswith(".py"):
        raise ValueError("select one tracked Python test file")
    # Don't put the repository on PYTHONPATH at interpreter startup: that
    # would let it supply startup modules (e.g. sitecustomize) or shadow
    # the installed test tools. Append it after loading trusted pytest.
    entry = "import sys; import pytest; sys.path.append('/workspace/repo'); sys.exit(pytest.main(sys.argv[1:]))"
    return [
        "/usr/bin/python3",
        "-P",
        "-c",
        entry,
        "-c",
        "/dev/null",
        "--rootdir=/workspace/repo",
        "--noconftest",
        "-p",
        "no:cacheprovider",
        "-p",
        "pytest_jsonreport.plugin",
        "--json-report",
        "--json-report-file=/workflo/artifacts/pytest-report.json",
        "--json-report-omit",
        "collectors",
        "log",
        "streams",
        "keywords",
        "warnings",
        "traceback",
        "--",
        f"/workspace/repo/{test_file}",
    ]


def build_local_policy(
    creator: RunCreatorV1,
    created_at: str,
    runtime_digest: str,
    seccomp_digest: str,
    test_file: str,
) -> ExecutionPolicyBundleV1:
    components = {
        "source": {
            "method": "local-git-blobs",
            "revision": "full-sha1",
            "links": "reject",
            "limit_files": MAX_SOURCE_FILES,
            "limit_bytes": MAX_SOURCE_BYTES,
            "secret_exclusion": "well-known-paths-v1",
        },
        "runtime": {
            "type": "namespaces",
            "image_digest": runtime_digest,
            "dependencies": "runtime-image-only",
            "seccomp_digest": seccomp_digest,
        },
        "resource": dict(RESOURCE_LIMITS),
        "command": {
            "test_file": test_file,
            "argv": pytest_argv(test_file),
            "environment": TEST_ENV.copy(),
        },
        "filesystem": {
            "source": "read-only",
            "rootfs": "read-only",
            "landlock": "required",
            "rules": [{"path": path, "access": access} for path, access in LANDLOCK_RULES],
        },
        "network": {"mode": "anonymous-isolated-netns", "egress": "deny"},
        "agent_capability": {"agent": False, "grants": [cap.value for cap in CAPABILITIES]},
        "model": {"allowed": False},
        "artifact": {
            "guest_input": "pytest-report-only",
            "max_report_bytes": MAX_REPORT_BYTES,
            "max_checks": MAX_CHECKS,
        },
        "evidence": {"retained": "local-metadata-only", "chain_version": 2},
        "retention": {"scratch": "destroy-after-run", "proof_bundle": "operator-managed"},
        "teardown": {
            "checks": ["process_scope_empty", "cgroups_removed", "workspace_removed"],
            "on_failure": "reject-signing",
        },
    }
    return ExecutionPolicyBundleV1(
        bundle_id=PROFILE_ID,
        organization_id=creator.organization_id,
        version="1",
        created_by=creator,
        created_at=created_at,
        components=tuple(
            PolicyComponentV1.build(
                component=PolicyComponentId(name),
                version="1",
                authority="local-dev-profile",
                payload=body,
            )
            for name, body in components.items()
        ),
    )


class SnapshotFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: DigestString
    size_bytes: int = Field(ge=0, strict=True)
    mode: Literal["100644", "100755"]

    _safe_path = field_validator("path")(validate_source_path)


class LocalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commit: str
    files: tuple[SnapshotFile, ...] = Field(min_length=1, max_length=MAX_SOURCE_FILES)

    _full_revision = field_validator("commit")(validate_revision)

    @model_validator(mode="after")
    def _ordered_files(self) -> LocalSnapshot:
        paths = [file.path for file in self.files]
        if paths != sorted(set(paths)) or sum(f.size_bytes for f in self.files) > MAX_SOURCE_BYTES:
            raise ValueError("snapshot files must be unique, sorted, and within the profile limits")
        return self

    def digest(self) -> str:
        return digest_of([item.model_dump(mode="json") for item in self.files])


class CheckObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=400, pattern=r"^[\x20-\x7e]+$")
    outcome: Literal["passed", "failed"]


class LocalCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    returncode: int = Field(ge=0, le=1, strict=True)
    checks: tuple[CheckObservation, ...] = Field(min_length=1, max_length=MAX_CHECKS)

    @model_validator(mode="after")
    def _complete_result(self) -> LocalCheckReport:
        ids = [item.node_id for item in self.checks]
        if ids != sorted(set(ids)) or self.returncode != int(
            any(item.outcome == "failed" for item in self.checks)
        ):
            raise ValueError("check IDs or exit status contradict the completed report")
        return self
