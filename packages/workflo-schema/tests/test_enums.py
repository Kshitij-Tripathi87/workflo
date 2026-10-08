"""Tests for enums module."""
import pytest
from workflo_schema import Goal, RunStatus, PlanTier, ApiKeyScope, ArtifactType, BrowserMode


class TestGoal:
    def test_members(self):
        assert Goal.SMOKE == "smoke"
        assert Goal.SECURITY == "security"
        assert Goal.INTEGRATION == "integration"
        assert Goal.MOBILE == "mobile"
        assert Goal.REGRESSION == "regression"
        assert Goal.CUSTOM == "custom"

    def test_from_string(self):
        assert Goal("smoke") == Goal.SMOKE
        assert Goal("security") == Goal.SECURITY

    def test_is_str_subclass(self):
        assert isinstance(Goal.SMOKE, str)


class TestRunStatus:
    def test_members(self):
        assert RunStatus.QUEUED == "queued"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"

    def test_from_string(self):
        assert RunStatus("running") == RunStatus.RUNNING
        assert RunStatus("completed") == RunStatus.COMPLETED

    def test_is_str(self):
        assert isinstance(RunStatus.QUEUED, str)


class TestPlanTier:
    def test_members(self):
        assert PlanTier.FREE == "free"
        assert PlanTier.PRO == "pro"
        assert PlanTier.TEAM == "team"
        assert PlanTier.ENTERPRISE == "enterprise"

    def test_defaults(self):
        assert PlanTier.FREE.value == "free"


class TestApiKeyScope:
    def test_members(self):
        assert ApiKeyScope.RUN_TESTS == "run_tests"
        assert ApiKeyScope.READ_REPORTS == "read_reports"
        assert ApiKeyScope.ADMIN == "admin"
        assert ApiKeyScope.WORKER == "worker"

    def test_from_string(self):
        assert ApiKeyScope("run_tests") == ApiKeyScope.RUN_TESTS
        assert ApiKeyScope("admin") == ApiKeyScope.ADMIN


class TestArtifactType:
    def test_members(self):
        assert ArtifactType.SCREENSHOT == "screenshot"
        assert ArtifactType.TRACE == "trace"
        assert ArtifactType.SOC2_REPORT == "soc2_report"
        assert ArtifactType.LOG == "log"
        assert ArtifactType.RESULTS_JSON == "results_json"

    def test_all_unique(self):
        values = [e.value for e in ArtifactType]
        assert len(values) == len(set(values))


class TestBrowserMode:
    def test_members(self):
        assert BrowserMode.CONTAINER == "container"
        assert BrowserMode.REAL_FLEET == "real_fleet"

    def test_from_string(self):
        assert BrowserMode("container") == BrowserMode.CONTAINER
        assert BrowserMode("real_fleet") == BrowserMode.REAL_FLEET