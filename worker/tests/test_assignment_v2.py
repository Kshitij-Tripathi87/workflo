"""SandboxAssignmentV2 binds agentic runtime identities to one attempt."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workflo_schema.contracts.agentic import AgentProfileRefV1
from workflo_worker_host.assignment import SandboxAssignmentV2


def test_v2_assignment_binds_profiles_plan_tools_and_capabilities(make_assignment):
    base = make_assignment().model_dump()
    base["schema_version"] = "2"
    assignment = SandboxAssignmentV2(
        **base,
        agent_registry_digest="sha256:" + "31" * 32,
        agent_profiles=(
            AgentProfileRefV1(
                profile_id="explorer", version="1.0.0",
                profile_digest="sha256:" + "32" * 32,
            ),
        ),
        agent_plan_digest="sha256:" + "33" * 32,
        tool_registry_digest="sha256:" + "34" * 32,
        capability_grant_digest="sha256:" + "35" * 32,
        model_manifest_digest="sha256:" + "36" * 32,
        model_artifact_digests=("sha256:" + "37" * 32,),
    )
    assert assignment.schema_version == "2"
    assert assignment.digest() == assignment.digest()
    changed = assignment.model_copy(update={"agent_plan_digest": "sha256:" + "38" * 32})
    assert changed.digest() != assignment.digest()


def test_v2_rejects_duplicate_profiles_and_unbound_model_artifacts(make_assignment):
    base = make_assignment().model_dump()
    base["schema_version"] = "2"
    ref = AgentProfileRefV1(
        profile_id="explorer", version="1.0.0",
        profile_digest="sha256:" + "32" * 32,
    )
    common = {
        "agent_registry_digest": "sha256:" + "31" * 32,
        "agent_plan_digest": "sha256:" + "33" * 32,
        "tool_registry_digest": "sha256:" + "34" * 32,
        "capability_grant_digest": "sha256:" + "35" * 32,
    }
    with pytest.raises(ValidationError):
        SandboxAssignmentV2(**base, **common, agent_profiles=(ref, ref))
    with pytest.raises(ValidationError):
        SandboxAssignmentV2(
            **base, **common, agent_profiles=(ref,),
            model_artifact_digests=("sha256:" + "37" * 32,),
        )
