"""Sandbox assignment contract tests (ADR-0022)."""

from __future__ import annotations

import pytest

from workflo_schema.contracts.runspec import NetworkPolicySpecV1

from workflo_worker_host.assignment import AssignmentError


def test_valid_assignment_round_trips(make_assignment):
    assignment = make_assignment()
    assert assignment.schema_version == "1"
    assert assignment.resource_limits.vcpus == 2


def test_digest_is_stable_and_signature_independent(make_assignment):
    from workflo_worker_host.assignment import SandboxAssignmentV1

    unsigned = make_assignment()
    signed = SandboxAssignmentV1(**{**unsigned.model_dump(), "signature": "c2ln"})
    assert signed.digest() == unsigned.digest()
    assert signed.digest() == signed.digest()


def test_any_field_change_changes_digest(make_assignment):
    a = make_assignment()
    b = make_assignment(policy_digest="sha256:" + "ff" * 32)
    assert a.digest() != b.digest()


def test_assignment_is_immutable(make_assignment):
    assignment = make_assignment()
    with pytest.raises(Exception):
        assignment.run_id = "run-2"  # type: ignore[misc]


def test_capabilities_must_be_unique(make_assignment):
    from workflo_schema.contracts.runspec import CapabilityId

    with pytest.raises(AssignmentError):
        make_assignment(
            capabilities=(CapabilityId.TESTS_EXECUTE, CapabilityId.TESTS_EXECUTE)
        )


def test_signature_verification_uses_injected_verifier(make_assignment):
    assignment = make_assignment(signature="c2ln")
    seen = {}

    def verify(key_id: str, message: bytes) -> bool:
        seen["key_id"] = key_id
        seen["message"] = message
        return True

    assert assignment.verify_signature(verify, "kms-key-1") is True
    assert seen["message"] == assignment.digest().encode("utf-8")


def test_unsigned_assignment_cannot_verify(make_assignment):
    assert make_assignment().verify_signature(lambda k, m: True) is False


def test_default_network_policy_is_deny(make_assignment):
    assignment = make_assignment()
    assert assignment.network_policy.default == "deny"
    assert assignment.network_policy.allowed_destinations == ()


def test_invalid_resource_limits_rejected(make_assignment):
    from workflo_worker_host.assignment import ResourceLimitsV1

    with pytest.raises(Exception):
        make_assignment(
            resource_limits=ResourceLimitsV1(
                vcpus=0, memory_mib=2048, disk_mib=10240, wall_clock_seconds=1800
            )
        )
