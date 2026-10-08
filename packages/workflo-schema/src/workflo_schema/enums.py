"""Enumerations shared across the Tenant Shield platform."""

from enum import Enum


class Goal(str, Enum):
    SMOKE = "smoke"
    SECURITY = "security"
    INTEGRATION = "integration"
    MOBILE = "mobile"
    REGRESSION = "regression"
    CUSTOM = "custom"
    FUNCTIONAL = "functional"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class ApiKeyScope(str, Enum):
    RUN_TESTS = "run_tests"
    READ_REPORTS = "read_reports"
    ADMIN = "admin"
    WORKER = "worker"


class ArtifactType(str, Enum):
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    SOC2_REPORT = "soc2_report"
    LOG = "log"
    RESULTS_JSON = "results_json"


class BrowserMode(str, Enum):
    CONTAINER = "container"
    REAL_FLEET = "real_fleet"
