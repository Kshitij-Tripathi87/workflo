"""Patch proposal / approval contract v1 (ADR-0021).

Approvals bind exact bytes, base revision, paths, and a one-time nonce;
any change invalidates the approval. Until the apply/retest pipeline
exists, proposals stop at READY_FOR_REVIEW and Workflo ships suggestions.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflo_schema.contracts.canonical import digest_of, sha256_digest
from workflo_schema.contracts.common import (
    CanonicalTimestamp,
    DigestString,
    IdString,
    RELATIVE_PATH_PATTERN,
    SCHEMA_VERSION,
)
from workflo_schema.contracts.events import ProducerIdentityV1
from workflo_schema.contracts.findings import ModelProvenanceV1

__all__ = [
    "PatchState",
    "TERMINAL_PATCH_STATES",
    "LEGAL_PATCH_TRANSITIONS",
    "can_transition_patch",
    "is_safe_relative_path",
    "extract_diff_paths",
    "PatchValidationCheckV1",
    "PatchValidationRecordV1",
    "PatchProposalV1",
    "ApprovalState",
    "PatchApprovalV1",
    "approval_matches",
]


class PatchState(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATING = "VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLYING_IN_SANDBOX = "APPLYING_IN_SANDBOX"
    PATCH_APPLIED_IN_SANDBOX = "PATCH_APPLIED_IN_SANDBOX"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    REGRESSION = "REGRESSION"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


TERMINAL_PATCH_STATES: frozenset[PatchState] = frozenset(
    {
        PatchState.REJECTED,
        PatchState.VERIFIED,
        PatchState.REGRESSION,
        PatchState.INCONCLUSIVE,
        PatchState.EXPIRED,
        PatchState.REVOKED,
    }
)

LEGAL_PATCH_TRANSITIONS: dict[PatchState, frozenset[PatchState]] = {
    PatchState.PROPOSED: frozenset(
        {PatchState.VALIDATING, PatchState.EXPIRED, PatchState.REVOKED}
    ),
    PatchState.VALIDATING: frozenset(
        {PatchState.READY_FOR_REVIEW, PatchState.REJECTED, PatchState.EXPIRED}
    ),
    PatchState.READY_FOR_REVIEW: frozenset(
        {
            PatchState.APPROVED,
            PatchState.REJECTED,
            PatchState.EXPIRED,
            PatchState.REVOKED,
        }
    ),
    # APPROVED is consumed by exactly one apply; a failed/interrupted apply
    # returns to review rather than silently reusing the approval.
    PatchState.APPROVED: frozenset(
        {PatchState.APPLYING_IN_SANDBOX, PatchState.REVOKED, PatchState.EXPIRED}
    ),
    PatchState.APPLYING_IN_SANDBOX: frozenset(
        {PatchState.PATCH_APPLIED_IN_SANDBOX, PatchState.REJECTED}
    ),
    PatchState.PATCH_APPLIED_IN_SANDBOX: frozenset({PatchState.VERIFYING}),
    PatchState.VERIFYING: frozenset(
        {PatchState.VERIFIED, PatchState.REGRESSION, PatchState.INCONCLUSIVE}
    ),
}


def can_transition_patch(source: PatchState, target: PatchState) -> bool:
    return target in LEGAL_PATCH_TRANSITIONS.get(source, frozenset())


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def is_safe_relative_path(path: str) -> bool:
    """Whether ``path`` is a normalized, safe repository-relative path."""
    if not path or len(path) > 512:
        return False
    if not re.match(RELATIVE_PATH_PATTERN, path):
        return False
    if path.startswith("/") or path.startswith("\\"):
        return False
    if "\\" in path or "\x00" in path:
        return False
    if _DRIVE_PREFIX.match(path):
        return False
    if not path.isascii():
        return False
    if unicodedata.normalize("NFC", path) != path:
        return False
    normalized = posixpath.normpath(path)
    if normalized != path or normalized.startswith("../") or normalized == "..":
        return False
    if any(segment in ("", ".", "..") for segment in path.split("/")):
        return False
    return True


_DIFF_PATH_RE = re.compile(r"^(?:---|\+\+\+) (?:a/|b/)?(.+?)(?:\t.*)?$", re.MULTILINE)


def extract_diff_paths(diff_text: str) -> list[str]:
    """Extract target paths from unified-diff file headers.

    Model-provided paths are untrusted: callers must validate every
    extracted path with :func:`is_safe_relative_path` and against the
    proposal's ``allowed_files`` before applying.
    """
    paths: list[str] = []
    for match in _DIFF_PATH_RE.finditer(diff_text):
        candidate = match.group(1).strip()
        if candidate == "/dev/null":
            continue
        if candidate.startswith('"') and candidate.endswith('"'):
            candidate = candidate[1:-1]
        if candidate not in paths:
            paths.append(candidate)
    return paths


class PatchValidationCheckV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(min_length=1, max_length=64)
    passed: bool
    detail: str | None = Field(default=None, max_length=500)


class PatchValidationRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    validator: ProducerIdentityV1
    validated_at: CanonicalTimestamp
    diff_digest: DigestString
    files_touched: int = Field(ge=0)
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    checks: tuple[PatchValidationCheckV1, ...] = Field(min_length=1)

    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


class PatchProposalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    proposal_id: IdString
    organization_id: IdString
    project_id: IdString
    origin_run_id: IdString
    origin_attempt_id: IdString
    finding_id: IdString

    base_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    base_snapshot_digest: DigestString
    target_ref: str = Field(min_length=1, max_length=255)
    patch_digest: DigestString
    diff_text: str = Field(min_length=1, max_length=200_000)
    allowed_files: tuple[str, ...] = Field(min_length=1)

    generator: ProducerIdentityV1
    model_provenance: ModelProvenanceV1 | None = None
    validation: PatchValidationRecordV1 | None = None
    state: PatchState = PatchState.PROPOSED
    created_at: CanonicalTimestamp
    expires_at: CanonicalTimestamp | None = None

    @model_validator(mode="after")
    def _digest_and_paths(self) -> "PatchProposalV1":
        if self.patch_digest != sha256_digest(self.diff_text.encode("utf-8")):
            raise ValueError("patch_digest does not match the exact diff bytes")
        if len(set(self.allowed_files)) != len(self.allowed_files):
            raise ValueError("allowed_files must be unique")
        unsafe = [path for path in self.allowed_files if not is_safe_relative_path(path)]
        if unsafe:
            raise ValueError(f"unsafe allowed_files entries: {unsafe}")
        diff_paths = extract_diff_paths(self.diff_text)
        outside = [path for path in diff_paths if path not in self.allowed_files]
        if outside:
            raise ValueError(
                f"diff touches files outside allowed_files: {outside}"
            )
        if self.state is PatchState.READY_FOR_REVIEW and self.validation is None:
            raise ValueError("READY_FOR_REVIEW requires a validation record")
        if self.validation is not None and self.validation.diff_digest != self.patch_digest:
            raise ValueError("validation record does not match the patch digest")
        return self

    def proposal_digest(self) -> str:
        """Content digest that approvals bind to.

        Binds identity, exact bytes, base revision, path set, and generator.
        Deliberately excludes the mutable ``state``/``validation`` fields so
        that ordinary workflow transitions do not invalidate an approval —
        while any byte, base, path, or target change does.
        """
        body = {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "origin_run_id": self.origin_run_id,
            "origin_attempt_id": self.origin_attempt_id,
            "finding_id": self.finding_id,
            "base_commit": self.base_commit,
            "base_snapshot_digest": self.base_snapshot_digest,
            "target_ref": self.target_ref,
            "patch_digest": self.patch_digest,
            "diff_text": self.diff_text,
            "allowed_files": list(self.allowed_files),
            "generator": self.generator.model_dump(mode="json"),
            "model_provenance": (
                self.model_provenance.model_dump(mode="json")
                if self.model_provenance is not None
                else None
            ),
        }
        return digest_of(body)


class ApprovalState(str, Enum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PatchApprovalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: IdString
    proposal_id: IdString
    proposal_digest: DigestString
    patch_digest: DigestString
    base_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    base_snapshot_digest: DigestString
    target_ref: str = Field(min_length=1, max_length=255)
    allowed_paths_digest: DigestString

    approved_by: IdString
    authorization_version: str = Field(min_length=1, max_length=64)
    approved_at: CanonicalTimestamp
    nonce: str = Field(min_length=16, max_length=128)
    state: ApprovalState = ApprovalState.ACTIVE


def approval_matches(proposal: PatchProposalV1, approval: PatchApprovalV1) -> bool:
    """Whether an approval still binds the exact proposal.

    Any byte, base-revision, path-set, or target change makes this False;
    a consumed/revoked/expired approval never matches.
    """
    if approval.state is not ApprovalState.ACTIVE:
        return False
    expected_paths_digest = digest_of(list(proposal.allowed_files))
    return (
        approval.proposal_id == proposal.proposal_id
        and approval.proposal_digest == proposal.proposal_digest()
        and approval.patch_digest == proposal.patch_digest
        and approval.base_commit == proposal.base_commit
        and approval.base_snapshot_digest == proposal.base_snapshot_digest
        and approval.target_ref == proposal.target_ref
        and approval.allowed_paths_digest == expected_paths_digest
    )
