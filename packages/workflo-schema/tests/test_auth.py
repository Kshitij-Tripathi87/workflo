"""Tests for auth models."""
from datetime import datetime, UTC
from workflo_schema import Organization, Project, ApiKey, PlanTier, ApiKeyScope


class TestOrganization:
    def test_basic(self):
        org = Organization(id="org-1", name="Acme Corp")
        assert org.id == "org-1"
        assert org.name == "Acme Corp"
        assert org.plan_tier == PlanTier.FREE
        assert org.created_at is None

    def test_override_tier(self):
        org = Organization(id="org-2", name="Enterprise Inc", plan_tier=PlanTier.ENTERPRISE)
        assert org.plan_tier == PlanTier.ENTERPRISE

    def test_with_created_at(self):
        now = datetime.now(UTC)
        org = Organization(id="org-3", name="Startup LLC", created_at=now)
        assert org.created_at == now

    def test_round_trip(self):
        org = Organization(id="org-4", name="Round Trip Co", plan_tier=PlanTier.PRO)
        reloaded = Organization.model_validate_json(org.model_dump_json())
        assert reloaded.id == "org-4"
        assert reloaded.plan_tier == PlanTier.PRO


class TestProject:
    def test_basic_create(self):
        proj = Project(id="proj-1", org_id="org-1", name="Web App")
        assert proj.id == "proj-1"
        assert proj.org_id == "org-1"
        assert proj.name == "Web App"
        assert proj.config_json == {}

    def test_with_config(self):
        config = {"BASE_URL": "https://app.example.com", "tenants": ["tenant_a", "tenant_b"]}
        proj = Project(id="proj-2", org_id="org-2", name="Dashboard", config_json=config)
        assert proj.config_json["BASE_URL"] == "https://app.example.com"
        assert proj.config_json["tenants"] == ["tenant_a", "tenant_b"]

    def test_round_trip(self):
        proj = Project(id="proj-3", org_id="org-3", name="Mobile", config_json={"key": "val"})
        reloaded = Project.model_validate_json(proj.model_dump_json())
        assert reloaded.id == "proj-3"
        assert reloaded.org_id == "org-3"
        assert reloaded.config_json == {"key": "val"}


class TestApiKey:
    def test_basic_create(self):
        key = ApiKey(id="key-1", project_id="proj-1", label="CI Pipeline")
        assert key.id == "key-1"
        assert key.project_id == "proj-1"
        assert key.label == "CI Pipeline"
        assert key.scopes == []
        assert key.last_used is None
        assert key.expires_at is None

    def test_default_label_empty(self):
        key = ApiKey(id="key-2", project_id="proj-2")
        assert key.label == ""

    def test_has_scope_present(self):
        key = ApiKey(id="key-3", project_id="proj-1", scopes=[ApiKeyScope.RUN_TESTS])
        assert key.has_scope(ApiKeyScope.RUN_TESTS) is True

    def test_has_scope_missing(self):
        key = ApiKey(id="key-4", project_id="proj-1", scopes=[ApiKeyScope.RUN_TESTS])
        assert key.has_scope(ApiKeyScope.ADMIN) is False

    def test_has_scope_multiple(self):
        key = ApiKey(
            id="key-5",
            project_id="proj-1",
            scopes=[ApiKeyScope.RUN_TESTS, ApiKeyScope.READ_REPORTS, ApiKeyScope.WORKER],
        )
        assert key.has_scope(ApiKeyScope.RUN_TESTS) is True
        assert key.has_scope(ApiKeyScope.READ_REPORTS) is True
        assert key.has_scope(ApiKeyScope.WORKER) is True
        assert key.has_scope(ApiKeyScope.ADMIN) is False

    def test_has_scope_empty_scopes(self):
        key = ApiKey(id="key-6", project_id="proj-2")
        assert key.has_scope(ApiKeyScope.RUN_TESTS) is False

    def test_with_dates(self):
        now = datetime.now(UTC)
        key = ApiKey(id="key-7", project_id="proj-3", last_used=now, expires_at=None)
        assert key.last_used == now
        assert key.expires_at is None

    def test_round_trip(self):
        key = ApiKey(
            id="key-8",
            project_id="proj-1",
            label="Prod Key",
            scopes=[ApiKeyScope.RUN_TESTS, ApiKeyScope.READ_REPORTS],
        )
        reloaded = ApiKey.model_validate_json(key.model_dump_json())
        assert reloaded.id == "key-8"
        assert ApiKeyScope.RUN_TESTS in reloaded.scopes
        assert ApiKeyScope.READ_REPORTS in reloaded.scopes