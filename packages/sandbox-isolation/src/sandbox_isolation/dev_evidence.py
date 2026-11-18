"""Pack and independently re-read local dev evidence without a sandbox runtime.

Only canonical records, not guest files, enter the proof directory. File
inventory, byte digests, ledger continuity and semantic cross-bindings are
checked both before signing and in the offline verifier.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter
from workflo_schema.contracts import (
    EVIDENCE_CHAIN_VERSION,
    EVIDENCE_GENESIS_INPUT,
    DetectorIdentityV1,
    EventType,
    EvidenceArtifactType,
    EvidenceArtifactV1,
    EvidenceClassification,
    EvidenceManifestV1,
    ExecutionPolicyBundleV1,
    FindingCategory,
    FindingV1,
    NetworkPolicySpecV1,
    PolicyComponentId,
    ProducerComponent,
    ProducerIdentityV1,
    RunEventV1,
    RunSpecV1,
    Severity,
    SourceProvider,
    ValidationState,
    VerificationStampV1,
)
from workflo_schema.contracts.canonical import canonical_bytes, digest_of, sha256_digest
from workflo_schema.contracts.common import DigestString
from workflo_schema.contracts.receipt import NamespaceTeardownVerificationV1
from workflo_schema.dev_check import (
    CAPABILITIES,
    PROFILE_ID,
    RETENTION,
    LocalCheckReport,
    LocalSnapshot,
    build_local_policy,
)

MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
_PAYLOAD_FILES = {
    "run-spec.json": EvidenceArtifactType.MANIFEST,
    "policy.json": EvidenceArtifactType.OTHER,
    "snapshot.json": EvidenceArtifactType.MANIFEST,
    "checks.json": EvidenceArtifactType.TEST_OUTPUT,
    "findings.json": EvidenceArtifactType.OTHER,
    "teardown.json": EvidenceArtifactType.TEARDOWN_EVIDENCE,
    "events.jsonl": EvidenceArtifactType.EVENT_LEDGER,
}
_STAGES = (
    (EventType.RUN_ADMITTED, ("run-spec.json", "policy.json")),
    (EventType.SOURCE_ACQUISITION_COMPLETED, ("snapshot.json",)),
    (EventType.TEST_COMPLETED, ("checks.json", "findings.json")),
    (EventType.SANDBOX_TEARDOWN_VERIFIED, ("teardown.json",)),
)


@dataclass(frozen=True)
class DevEvidence:
    spec: RunSpecV1
    policy: ExecutionPolicyBundleV1
    snapshot: LocalSnapshot
    report: LocalCheckReport
    teardown: NamespaceTeardownVerificationV1
    snapshot_at: str
    checks_at: str

    @property
    def attempt_id(self) -> str:
        return f"attempt-{self.spec.idempotency_key}"

    @property
    def sandbox_id(self) -> str:
        return f"sbx-{self.spec.idempotency_key}"

    @property
    def scope(self) -> dict[str, str]:
        return {
            "organization_id": self.spec.organization_id,
            "project_id": self.spec.project_id,
            "run_id": self.spec.run_id,
            "attempt_id": self.attempt_id,
        }

    def findings(self) -> list[FindingV1]:
        judge = DetectorIdentityV1(
            component=ProducerComponent.JUDGE, version="1", ruleset_id=PROFILE_ID
        )
        return [
            FindingV1(
                **self.scope,
                finding_id=f"finding-{self.spec.idempotency_key}-{index}",
                source_revision=self.snapshot.commit,
                snapshot_digest=self.snapshot.digest(),
                category=FindingCategory.VERIFIED_FAILURE,
                severity=Severity.MEDIUM,
                title=check.node_id,
                reproduction_reference=check.node_id,
                expected_behavior="The admitted pytest check passes.",
                observed_behavior="The named check failed in pytest's call phase.",
                evidence_refs=("checks",),
                detector=judge,
                created_at=self.checks_at,
                verified_by=VerificationStampV1(
                    verifier=judge,
                    criteria_id="complete-pytest-call-v1",
                    verified_at=self.checks_at,
                    procedure="Match the isolated pytest exit status, admitted test file, completed phases, and counts.",
                ),
            )
            for index, check in enumerate(self.report.checks, start=1)
            if check.outcome == "failed"
        ]

    def validate(self) -> None:
        spec = self.spec
        token = spec.idempotency_key
        if (
            not re.fullmatch(r"[a-f0-9]{32}", token)
            or spec.run_id != f"run-{token}"
            or spec.organization_id != "local-dev"
            or spec.project_id != "local-project"
            or spec.created_by.organization_id != spec.organization_id
            or spec.created_by.user_id != "local-operator"
            or spec.profile_id != PROFILE_ID
            or spec.resource_profile != PROFILE_ID
            or spec.capabilities != CAPABILITIES
            or spec.retention != RETENTION
            or spec.network_policy != NetworkPolicySpecV1()
            or spec.model_artifacts
        ):
            raise ValueError("evidence run spec does not match the local development profile")
        source = spec.source
        if (
            source.provider is not SourceProvider.GENERIC_GIT
            or source.url is not None
            or source.commit != self.snapshot.commit
            or source.ref != source.commit
            or source.snapshot_digest is not None  # admission predates materialization
        ):
            raise ValueError("source snapshot does not match the admitted revision")
        components = {
            component.component: component.payload for component in self.policy.components
        }
        test_file = components[PolicyComponentId.COMMAND].get("test_file")
        if not isinstance(test_file, str):
            raise ValueError("admitted test file is missing")
        seccomp = TypeAdapter(DigestString).validate_python(
            components[PolicyComponentId.RUNTIME].get("seccomp_digest")
        )
        expected_policy = build_local_policy(
            spec.created_by, spec.created_at, spec.runtime_image_digest, seccomp, test_file
        )
        if self.policy != expected_policy or spec.policy_digest != expected_policy.digest():
            raise ValueError("execution policy is invalid or differs from admission")
        if test_file not in {file.path for file in self.snapshot.files} or any(
            not check.node_id.startswith(f"{test_file}::") for check in self.report.checks
        ):
            raise ValueError("checks do not belong to the admitted test file")
        verifier = ProducerIdentityV1(
            component=ProducerComponent.HOST_WORKER, instance_id=self.sandbox_id, version=PROFILE_ID
        )
        if (
            not self.teardown.all_passed()
            or self.teardown.verifier != verifier
            or self.teardown.verification_id != f"teardown-{token}"
            or not spec.created_at
            <= self.snapshot_at
            <= self.checks_at
            <= self.teardown.observed_at
        ):
            raise ValueError("missing, failed, or mismatched host teardown observations")

    def encode(self) -> tuple[dict[str, bytes], EvidenceManifestV1]:
        self.validate()
        files = {
            "run-spec.json": canonical_bytes(self.spec.model_dump(mode="json")),
            "policy.json": canonical_bytes(self.policy.model_dump(mode="json")),
            "snapshot.json": canonical_bytes(self.snapshot.model_dump(mode="json")),
            "checks.json": canonical_bytes(self.report.model_dump(mode="json")),
            "findings.json": canonical_bytes([f.model_dump(mode="json") for f in self.findings()]),
            "teardown.json": canonical_bytes(self.teardown.model_dump(mode="json")),
        }
        times = (self.spec.created_at, self.snapshot_at, self.checks_at, self.teardown.observed_at)
        ledger_root = sha256_digest(EVIDENCE_GENESIS_INPUT)
        ledger = []
        for seq, ((kind, refs), occurred_at) in enumerate(
            zip(_STAGES, times, strict=True), start=1
        ):
            event = RunEventV1.build(
                **self.scope,
                sandbox_id=self.sandbox_id,
                sequence_number=seq,
                event_id=f"{self.spec.run_id}-evt-{seq}",
                correlation_id=self.spec.run_id,
                event_type=kind,
                occurred_at=occurred_at,
                producer=self.teardown.verifier,
                payload={"artifacts": {name: sha256_digest(files[name]) for name in refs}},
            )
            record = {
                "v": EVIDENCE_CHAIN_VERSION,
                "event": event.model_dump(mode="json"),
                "prev_hash": ledger_root,
            }
            ledger_root = digest_of(record)
            ledger.append(canonical_bytes({**record, "event_hash": ledger_root}) + b"\n")
        files["events.jsonl"] = b"".join(ledger)
        artifacts = tuple(
            EvidenceArtifactV1(
                **self.scope,
                sandbox_id=self.sandbox_id,
                artifact_id=Path(name).stem,
                artifact_type=kind,
                media_type="application/x-ndjson"
                if name.endswith(".jsonl")
                else "application/json",
                size_bytes=len(files[name]),
                sha256=sha256_digest(files[name]),
                producer=self.teardown.verifier,
                stage="local-check",
                source_revision=self.snapshot.commit,
                snapshot_digest=self.snapshot.digest(),
                policy_digest=self.spec.policy_digest,
                runtime_image_digest=self.spec.runtime_image_digest,
                classification=EvidenceClassification.EXECUTION_EVIDENCE,
                retention_policy_id=RETENTION.retention_policy_id,
                validation_state=ValidationState.VALIDATED,
                object_ref=name,
                created_at=self.teardown.observed_at,
            )
            for name, kind in _PAYLOAD_FILES.items()
        )
        manifest = EvidenceManifestV1(
            **self.scope,
            manifest_id=f"manifest-{self.spec.idempotency_key}",
            created_at=self.teardown.observed_at,
            artifacts=artifacts,
            ledger_chain_version=EVIDENCE_CHAIN_VERSION,
            ledger_root=ledger_root,
            ledger_checkpoint=len(ledger),
            events_count=len(ledger),
        )
        files["manifest.json"] = canonical_bytes(manifest.model_dump(mode="json"))
        return files, manifest


def write_dev_evidence(directory: Path, evidence: DevEvidence) -> str:
    """Persist exactly one bundle, returning its in-memory host-side anchor."""
    files, manifest = evidence.encode()
    directory.mkdir(mode=0o700, exist_ok=False)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    return manifest.digest()


def _read_evidence_file(path: Path) -> bytes:
    # O_NOFOLLOW and O_NONBLOCK protect Linux verifiers even if the bundle
    # changes after inventory. lstat also rejects links on other platforms.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"expected a regular evidence file: {path.name}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        data = stream.read(MAX_EVIDENCE_FILE_BYTES + 1)
    if len(data) > MAX_EVIDENCE_FILE_BYTES:
        raise ValueError(f"evidence file too large: {path.name}")
    return data


def validate_dev_evidence(directory: Path) -> tuple[DevEvidence, EvidenceManifestV1, str]:
    """Rebuild the exact expected evidence and ledger from scoped observations.

    Never import the producer or accept its `success`/manifest hashes as proof.
    The caller must anchor the result to a trusted signed or in-memory digest.
    """
    expected_names = set(_PAYLOAD_FILES) | {"manifest.json"}
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or {item.name for item in directory.iterdir()} != expected_names
    ):
        raise ValueError("missing or unexpected files in the development evidence bundle")
    files = {name: _read_evidence_file(directory / name) for name in expected_names}
    try:
        events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
        if len(events) != len(_STAGES):
            raise ValueError("wrong ledger length")
        evidence = DevEvidence(
            spec=RunSpecV1.model_validate_json(files["run-spec.json"]),
            policy=ExecutionPolicyBundleV1.model_validate_json(files["policy.json"]),
            snapshot=LocalSnapshot.model_validate_json(files["snapshot.json"]),
            report=LocalCheckReport.model_validate_json(files["checks.json"]),
            teardown=NamespaceTeardownVerificationV1.model_validate_json(files["teardown.json"]),
            snapshot_at=events[1]["event"]["occurred_at"],
            checks_at=events[2]["event"]["occurred_at"],
        )
        rebuilt, manifest = evidence.encode()
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError(
            "invalid development evidence, policy, ledger, or teardown record"
        ) from exc
    for name in sorted(expected_names):
        if rebuilt[name] != files[name]:
            raise ValueError(f"development evidence mismatch: {name}")
    return evidence, manifest, sha256_digest(files["findings.json"])
