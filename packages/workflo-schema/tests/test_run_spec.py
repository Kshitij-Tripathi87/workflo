"""Tests for run_spec models."""
import json
import pytest
from pydantic import ValidationError
from workflo_schema import (
    RunSpec,
    RunConfig,
    TestTargets,
    ArtifactsConfig,
    Goal,
    BrowserMode,
)


class TestRunSpecRoundTrip:
    def test_full_spec_serialization(self):
        spec = RunSpec(
            goal=Goal.SECURITY,
            markers=["security", "critical"],
            env={"BASE_URL": "https://example.com", "TENANT_A_ID": "t-001"},
            targets=TestTargets(include=["tests/**/*.py"], exclude=["tests/fixtures/**"]),
            config=RunConfig(
                browsers=["chromium", "firefox"],
                mobile_devices=["iPhone 14"],
                parallelism=8,
                retries=3,
                timeout_seconds=600,
                browser_mode=BrowserMode.CONTAINER,
            ),
            artifacts=ArtifactsConfig(
                screenshots=False,
                traces="always",
                soc2_report=True,
                logs=True,
            ),
            project_id="proj-abc123",
            repo_url="https://github.com/acme/workflo.git",
            commit_sha="abc123def456",
        )

        dumped = spec.model_dump()
        reloaded = RunSpec(**dumped)

        assert reloaded.goal == Goal.SECURITY
        assert reloaded.markers == ["security", "critical"]
        assert reloaded.env == {"BASE_URL": "https://example.com", "TENANT_A_ID": "t-001"}
        assert reloaded.targets.include == ["tests/**/*.py"]
        assert reloaded.targets.exclude == ["tests/fixtures/**"]
        assert reloaded.config.parallelism == 8
        assert reloaded.config.browser_mode == BrowserMode.CONTAINER
        assert reloaded.artifacts.traces == "always"
        assert reloaded.project_id == "proj-abc123"
        assert reloaded.repo_url == "https://github.com/acme/workflo.git"
        assert reloaded.commit_sha == "abc123def456"

    def test_minimal_spec_round_trip(self):
        min_spec = RunSpec(goal=Goal.CUSTOM)
        dumped = min_spec.model_dump()
        reloaded = RunSpec(**dumped)
        assert reloaded.goal == Goal.CUSTOM
        assert reloaded.markers == []
        assert reloaded.env == {}
        assert reloaded.project_id is None
        assert reloaded.repo_url is None
        assert reloaded.commit_sha is None

    def test_multiple_goals_round_trip(self):
        for goal in Goal:
            spec = RunSpec(goal=goal, project_id="test-proj")
            json_str = spec.model_dump_json()
            reloaded = RunSpec.model_validate_json(json_str)
            assert reloaded.goal == goal
            assert reloaded.project_id == "test-proj"


class TestRunSpecDefaults:
    def test_default_targets(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.targets.include == []
        assert spec.targets.exclude == []

    def test_default_browsers(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.config.browsers == ["chromium"]

    def test_default_parallelism(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.config.parallelism == 4

    def test_default_retries(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.config.retries == 2

    def test_default_timeout(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.config.timeout_seconds == 300

    def test_default_browser_mode(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.config.browser_mode == BrowserMode.CONTAINER

    def test_default_artifacts(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.artifacts.screenshots is True
        assert spec.artifacts.traces == "on-failure"
        assert spec.artifacts.soc2_report is True
        assert spec.artifacts.logs is True

    def test_default_project_id_none(self):
        spec = RunSpec(goal=Goal.SECURITY)
        assert spec.project_id is None


class TestRunSpecValidation:
    def test_missing_goal_raises(self):
        with pytest.raises(ValidationError):
            RunSpec()

    def test_invalid_goal_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(goal="not_a_valid_goal")

    def test_parallelism_below_min_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(parallelism=0),
            )

    def test_parallelism_above_max_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(parallelism=65),
            )

    def test_retries_below_min_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(retries=-1),
            )

    def test_retries_above_max_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(retries=11),
            )

    def test_timeout_below_min_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(timeout_seconds=5),
            )

    def test_timeout_above_max_raises(self):
        with pytest.raises(ValidationError):
            RunSpec(
                goal=Goal.SECURITY,
                config=RunConfig(timeout_seconds=3601),
            )


class TestJsonSerialization:
    def test_serialize_deserialize_full(self):
        spec = RunSpec(
            goal=Goal.CUSTOM,
            markers=["custom-tag"],
            env={"KEY": "value"},
            targets=TestTargets(include=["t.py"]),
            config=RunConfig(browsers=["firefox"], parallelism=2),
            repo_url="https://github.com/test/repo",
        )
        s = spec.model_dump_json()
        reloaded = RunSpec.model_validate_json(s)
        assert reloaded.goal == Goal.CUSTOM
        assert reloaded.config.parallelism == 2
        assert reloaded.config.browsers == ["firefox"]

    def test_enum_serialized_as_string(self):
        spec = RunSpec(goal=Goal.MOBILE)
        data = json.loads(spec.model_dump_json())
        assert data["goal"] == "mobile"

    def test_null_optional_fields(self):
        spec = RunSpec(goal=Goal.SECURITY)
        data = json.loads(spec.model_dump_json())
        assert data["project_id"] is None
        assert data["repo_url"] is None
        assert data["commit_sha"] is None