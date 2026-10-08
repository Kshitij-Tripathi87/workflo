"""Tests for the frozen REST contract — `workflo_schema.api`.

This is the public, versioned wire-format between the control-plane, any
frontend/SDK, and the CLI's `--via-api` mode. Every change to `api.py` is
a breaking change for external consumers, so these tests pin the contract
down to the exact fields, the probe-group vocabulary, the
public->internal mapping, and the validation/error semantics documented in
`docs/api_contract.md`.

Every JSON example in `docs/api_contract.md` is instantiated here so the
docs and the code can't drift.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from workflo_schema.api import (
    RunRequest,
    RunStatus,
    _public_goal,
    _public_to_internal,
    _VALID_PROBE_GROUPS,
)
from workflo_schema.sandbox import SandboxSpec


# --------------------------------------------------------------------
# Probe-group vocabulary
# --------------------------------------------------------------------


class TestProbeGroupVocabulary:
    def test_valid_probe_groups_accepted(self):
        for g in ["test", "security", "deep-test", "aggressive-test", "web"]:
            req = RunRequest(repo_url="https://x/r.git", probe_groups=[g])
            assert g in req.probe_groups

    def test_empty_probe_groups_rejected(self):
        with pytest.raises(ValidationError):
            RunRequest(repo_url="https://x/r.git", probe_groups=[])

    @pytest.mark.parametrize("bad", ["Test", "TEST", "fuzz", "smoke", "surface", "deep", "", " web"])
    def test_unknown_probe_group_rejected(self, bad):
        # Pydantic rejects unknown groups at the Literal type level ("Input
        # should be 'test', ...") BEFORE the custom field_validator message
        # runs. Either rejection path is fail-closed — the value must never
        # be accepted.
        with pytest.raises(ValidationError) as ei:
            RunRequest(repo_url="https://x/r.git", probe_groups=[bad])
        assert "probe_groups" in str(ei.value)

    def test_vocabulary_is_exactly_the_five(self):
        assert _VALID_PROBE_GROUPS == frozenset(
            {"test", "security", "deep-test", "aggressive-test", "web"}
        )

    def test_security_is_composable_with_functional_tiers(self):
        for tier in ["test", "deep-test", "aggressive-test", "web"]:
            req = RunRequest(repo_url="https://x/r.git", probe_groups=[tier, "security"])
            assert set(req.probe_groups) == {tier, "security"}

    def test_security_alone_is_accepted(self):
        # security without a functional tier is allowed at the schema level;
        # any "must include a functional tier" rule is the API server's job,
        # not the model's.
        req = RunRequest(repo_url="https://x/r.git", probe_groups=["security"])
        assert req.probe_groups == ["security"]


# --------------------------------------------------------------------
# Field validation
# --------------------------------------------------------------------


class TestRunRequestFieldValidation:
    def test_repo_url_required(self):
        with pytest.raises(ValidationError):
            RunRequest(probe_groups=["test"])

    def test_probe_groups_required(self):
        with pytest.raises(ValidationError):
            RunRequest(repo_url="https://x/r.git")

    def test_commit_sha_max_64_chars(self):
        with pytest.raises(ValidationError):
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["test"],
                commit_sha="a" * 65,
            )

    def test_commit_sha_64_chars_accepted(self):
        req = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["test"],
            commit_sha="a" * 64,
        )
        assert len(req.commit_sha) == 64

    @pytest.mark.parametrize("bad", [0, -1, 70000, 99999])
    def test_port_out_of_range_rejected(self, bad):
        with pytest.raises(ValidationError):
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["web"],
                start_command="python app.py",
                port=bad,
            )

    @pytest.mark.parametrize("ok", [1, 80, 5000, 65535])
    def test_port_in_range_accepted(self, ok):
        req = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["web"],
            start_command="python app.py",
            port=ok,
        )
        assert req.port == ok


# --------------------------------------------------------------------
# Public -> internal probe-group mapping & goal selection
# --------------------------------------------------------------------


class TestPublicToInternalMapping:
    @pytest.mark.parametrize(
        "public,internal",
        [
            ("test", "surface"),
            ("security", "security"),
            ("deep-test", "deep"),
            ("aggressive-test", "aggressive"),
            ("web", "web"),
        ],
    )
    def test_each_group_maps_to_internal(self, public, internal):
        assert _public_to_internal(public) == internal

    @pytest.mark.parametrize(
        "groups,goal",
        [
            (["test"], "test"),
            (["security", "test"], "test"),
            (["deep-test"], "deep"),
            (["aggressive-test"], "aggressive"),
            (["web"], "web"),
            (["web", "security"], "web"),
            (["security"], "security"),
        ],
    )
    def test_goal_priority_resolution(self, groups, goal):
        assert _public_goal(groups) == goal


# --------------------------------------------------------------------
# to_sandbox_spec
# --------------------------------------------------------------------


class TestToSandboxSpec:
    def test_returns_sandbox_spec_instance(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test"]
        ).to_sandbox_spec()
        assert isinstance(spec, SandboxSpec)

    def test_sandbox_id_is_a_uuid_string(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test"]
        ).to_sandbox_spec()
        # uuid4 string is 36 chars with hyphens
        assert isinstance(spec.sandbox_id, str)
        assert spec.sandbox_id.count("-") == 4
        assert len(spec.sandbox_id) == 36

    def test_each_call_gets_a_unique_sandbox_id(self):
        a = RunRequest(repo_url="u", probe_groups=["test"]).to_sandbox_spec()
        b = RunRequest(repo_url="u", probe_groups=["test"]).to_sandbox_spec()
        assert a.sandbox_id != b.sandbox_id

    def test_repo_url_and_commit_sha_pass_through(self):
        spec = RunRequest(
            repo_url="https://github.com/ex/r.git",
            probe_groups=["test"],
            commit_sha="abc123",
        ).to_sandbox_spec()
        assert spec.repo_url == "https://github.com/ex/r.git"
        assert spec.commit_sha == "abc123"

    def test_commit_sha_defaults_to_none(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test"]
        ).to_sandbox_spec()
        assert spec.commit_sha is None

    def test_internal_probe_groups_use_executor_vocabulary(self):
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["test", "security"],
        ).to_sandbox_spec()
        # Public "test" -> internal "surface"; security stays security.
        assert spec.run_spec["probe_groups"] == ["surface", "security"]

    def test_deep_test_maps_to_deep_internal(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["deep-test"]
        ).to_sandbox_spec()
        assert spec.run_spec["probe_groups"] == ["deep"]

    def test_goal_reflects_probe_group(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["deep-test"]
        ).to_sandbox_spec()
        assert spec.run_spec["goal"] == "deep"

    def test_defaults_applied_when_config_absent(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test"]
        ).to_sandbox_spec()
        assert spec.timeout_seconds == 600
        assert spec.memory_mb == 2048
        assert spec.cpu_cores == 2.0
        assert spec.allowed_egress_hosts == []

    def test_config_overrides_pass_through(self):
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["test"],
            config={"timeout_seconds": 300, "memory_mb": 1024, "cpu_cores": 4.0},
        ).to_sandbox_spec()
        assert spec.timeout_seconds == 300
        assert spec.memory_mb == 1024
        assert spec.cpu_cores == 4.0

    def test_unknown_config_keys_ignored(self):
        # Unknown keys must not crash and must not pollute SandboxSpec.
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["test"],
            config={"timeout_seconds": 120, "magic_flag": True, "queue": "gpu"},
        ).to_sandbox_spec()
        assert spec.timeout_seconds == 120

    def test_out_of_range_config_rejected_by_sandbox_spec(self):
        with pytest.raises((ValidationError, ValueError)):
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["test"],
                config={"timeout_seconds": 99999},  # > 3600
            ).to_sandbox_spec()

    def test_run_spec_shape(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test"]
        ).to_sandbox_spec()
        rs = spec.run_spec
        assert rs["env"] == {}
        assert rs["targets"] == {"include": [], "exclude": []}
        assert rs["markers"] == []
        assert rs["config"] == {}
        assert rs["artifacts"] == {}


# --------------------------------------------------------------------
# Web tier: env injection + fail-fast validation
# --------------------------------------------------------------------


class TestWebTierSpecGeneration:
    def test_web_sets_workflo_env_vars(self):
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["web"],
            start_command="python app.py",
            port=5000,
        ).to_sandbox_spec()
        env = spec.run_spec["env"]
        assert env["WORKFLO_START_COMMAND"] == "python app.py"
        # port is stringified (env vars are strings).
        assert env["WORKFLO_WEB_PORT"] == "5000"
        assert isinstance(env["WORKFLO_WEB_PORT"], str)

    def test_web_maps_to_internal_web_group(self):
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["web"],
            start_command="python app.py",
            port=5000,
        ).to_sandbox_spec()
        assert spec.run_spec["probe_groups"] == ["web"]
        assert spec.run_spec["goal"] == "web"

    def test_web_missing_start_command_raises_value_error(self):
        with pytest.raises(ValueError) as ei:
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["web"],
                port=5000,
            ).to_sandbox_spec()
        msg = str(ei.value)
        assert "web" in msg
        assert "start_command" in msg
        assert "missing required fields" in msg

    def test_web_missing_port_raises_value_error(self):
        with pytest.raises(ValueError) as ei:
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["web"],
                start_command="python app.py",
            ).to_sandbox_spec()
        msg = str(ei.value)
        assert "port" in msg
        assert "missing required fields" in msg

    def test_web_missing_both_names_both_in_error(self):
        with pytest.raises(ValueError) as ei:
            RunRequest(
                repo_url="https://x/r.git",
                probe_groups=["web"],
            ).to_sandbox_spec()
        msg = str(ei.value)
        assert "start_command" in msg
        assert "port" in msg

    def test_web_with_security_composes(self):
        spec = RunRequest(
            repo_url="https://x/r.git",
            probe_groups=["web", "security"],
            start_command="python app.py",
            port=5000,
        ).to_sandbox_spec()
        assert spec.run_spec["probe_groups"] == ["web", "security"]
        # web beats security in goal priority.
        assert spec.run_spec["goal"] == "web"
        assert spec.run_spec["env"]["WORKFLO_START_COMMAND"] == "python app.py"

    def test_non_web_run_has_no_workflo_env(self):
        spec = RunRequest(
            repo_url="https://x/r.git", probe_groups=["test", "security"]
        ).to_sandbox_spec()
        assert spec.run_spec["env"] == {}
        assert "WORKFLO_START_COMMAND" not in spec.run_spec["env"]


# --------------------------------------------------------------------
# RunStatus
# --------------------------------------------------------------------


class TestRunStatus:
    def test_queued_response_shape(self):
        now = datetime(2026, 8, 21, 16, 42, 11, 123456, tzinfo=timezone.utc)
        st = RunStatus(run_id="run-1", status="queued", created_at=now)
        assert st.run_id == "run-1"
        assert st.status == "queued"
        assert st.receipt is None
        assert st.error is None
        assert st.created_at == now

    def test_completed_carries_receipt(self):
        st = RunStatus(
            run_id="run-1",
            status="completed",
            created_at=datetime.now(timezone.utc),
            receipt={"sandbox_id": "sb-1", "total": 4, "passed": 4},
        )
        assert st.receipt is not None
        assert st.receipt["passed"] == 4
        assert st.error is None

    def test_failed_carries_error(self):
        st = RunStatus(
            run_id="run-1",
            status="failed",
            created_at=datetime.now(timezone.utc),
            error="Ollama did not respond within 30s",
        )
        assert st.error == "Ollama did not respond within 30s"
        assert st.receipt is None

    @pytest.mark.parametrize("bad", ["queued-up", "done", "ok", "success", "", "Created"])
    def test_invalid_status_rejected(self, bad):
        with pytest.raises(ValidationError):
            RunStatus(run_id="run-1", status=bad, created_at=datetime.now(timezone.utc))

    def test_completed_with_failed_tests_still_completed(self):
        # Contract: status reflects infrastructure, not test outcomes. A run
        # whose tests failed is completed-with-a-receipt, NOT failed.
        st = RunStatus(
            run_id="run-1",
            status="completed",
            created_at=datetime.now(timezone.utc),
            receipt={"success": False, "report": {"failed": 2, "passed": 0}},
        )
        assert st.status == "completed"
        assert st.receipt is not None

    def test_json_round_trip(self):
        now = datetime(2026, 8, 21, 16, 42, 11, 123456, tzinfo=timezone.utc)
        st = RunStatus(run_id="r", status="completed", created_at=now, receipt={"k": "v"})
        dumped = st.model_dump(mode="json")
        rebuilt = RunStatus.model_validate(dumped)
        assert rebuilt.run_id == "r"
        assert rebuilt.status == "completed"
        assert rebuilt.receipt == {"k": "v"}


# --------------------------------------------------------------------
# Documentation examples — keep docs and code in lockstep
# (every JSON block in docs/api_contract.md is instantiated here)
# --------------------------------------------------------------------


class TestDocsApiContractExamples:
    def test_post_runs_request_example_parses(self):
        # The first JSON example in the POST /v1/runs section.
        req = RunRequest(
            repo_url="https://github.com/example/my-saas-app.git",
            probe_groups=["test", "security"],
            commit_sha="a1b2c3d4e5f6",
            config={"timeout_seconds": 300, "memory_mb": 2048},
        )
        spec = req.to_sandbox_spec()
        assert spec.timeout_seconds == 300
        assert spec.memory_mb == 2048
        assert spec.repo_url == "https://github.com/example/my-saas-app.git"
        assert spec.commit_sha == "a1b2c3d4e5f6"

    def test_post_runs_web_example_parses(self):
        # The "With web" JSON example.
        req = RunRequest(
            repo_url="https://github.com/example/my-saas-app.git",
            probe_groups=["web", "security"],
            start_command="python app.py",
            port=5000,
        )
        spec = req.to_sandbox_spec()
        assert spec.run_spec["env"]["WORKFLO_START_COMMAND"] == "python app.py"
        assert spec.run_spec["env"]["WORKFLO_WEB_PORT"] == "5000"
        assert spec.run_spec["probe_groups"] == ["web", "security"]

    def test_web_validation_failure_message_matches_docs(self):
        # The docs' 400 detail message must match what the code raises.
        with pytest.raises(ValueError) as ei:
            RunRequest(
                repo_url="https://github.com/example/my-saas-app.git",
                probe_groups=["web", "security"],
            ).to_sandbox_spec()
        msg = str(ei.value)
        # The docs' 400 body starts with this exact prefix.
        assert msg.startswith("probe_groups includes 'web' but missing required fields")
        assert "start_command" in msg
        assert "port" in msg

    def test_queued_response_example_shape(self):
        # The 200 OK response example from the docs.
        st = RunStatus(
            run_id="7f3a2b8c-1234-5678-9abc-def012345678",
            status="queued",
            created_at=datetime(2026, 8, 21, 16, 42, 11, 123456, tzinfo=timezone.utc),
        )
        data = st.model_dump(mode="json")
        assert data["run_id"] == "7f3a2b8c-1234-5678-9abc-def012345678"
        assert data["status"] == "queued"
        assert data["receipt"] is None
        assert data["error"] is None

    def test_completed_response_example_shape(self):
        st = RunStatus(
            run_id="7f3a2b8c-1234-5678-9abc-def012345678",
            status="completed",
            created_at=datetime(2026, 8, 21, 16, 42, 11, 123456, tzinfo=timezone.utc),
            receipt={},
        )
        assert st.model_dump(mode="json")["receipt"] == {}

    def test_failed_response_example_shape(self):
        st = RunStatus(
            run_id="7f3a2b8c-1234-5678-9abc-def012345678",
            status="failed",
            created_at=datetime(2026, 8, 21, 16, 42, 11, 123456, tzinfo=timezone.utc),
            error="Ollama did not respond within 30s; receipt not produced.",
        )
        data = st.model_dump(mode="json")
        assert data["error"] == "Ollama did not respond within 30s; receipt not produced."
        assert data["receipt"] is None


# --------------------------------------------------------------------
# Serialization boundary — RunStatus.receipt stays a plain dict
# (the control-plane stores it via json.loads(result.to_json()), and the
# CLI prints it; it must round-trip as a dict, not a typed model)
# --------------------------------------------------------------------


class TestReceiptIsPlainDict:
    def test_receipt_accepts_arbitrary_dict(self):
        receipt = {
            "sandbox_id": "sb-1",
            "signature": "abc",
            "web_probes": {"base_url": "http://127.0.0.1:5000", "probes": []},
            "nested": {"deeply": {"typed": False}},
        }
        st = RunStatus(
            run_id="r",
            status="completed",
            created_at=datetime.now(timezone.utc),
            receipt=receipt,
        )
        assert st.receipt == receipt
        # Round-trips through JSON without losing the dict-ness or contents.
        assert RunStatus.model_validate(st.model_dump(mode="json")).receipt == receipt
