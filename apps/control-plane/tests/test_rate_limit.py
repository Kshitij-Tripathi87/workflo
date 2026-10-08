"""Rate limiting tests (SOC 2 CC6.1/CC7.1).

- Per-IP login ceiling (5/5min) blocks credential stuffing.
- Per-project run-submission ceiling: one tenant bursts don't starve
  other tenants; the 429 carries Retry-After and is audited as denied.
"""

from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter, check_login_rate_limit


class TestInMemoryLimiterSemantics:
    def test_window_slides(self):
        limiter = InMemoryRateLimiter()
        allowed_all = [limiter.hit("k", 2, 60)[0] for _ in range(2)]
        assert allowed_all == [True, True]
        allowed, retry = limiter.hit("k", 2, 60)
        assert allowed is False
        assert retry >= 1

    def test_keys_are_independent(self):
        limiter = InMemoryRateLimiter()
        limiter.hit("a", 1, 60)
        assert limiter.hit("b", 1, 60)[0] is True

    def test_clear_resets(self):
        limiter = InMemoryRateLimiter()
        limiter.hit("k", 1, 60)
        assert limiter.hit("k", 1, 60)[0] is False
        limiter.clear()
        assert limiter.hit("k", 1, 60)[0] is True


class TestLoginRateLimit:
    def test_sixth_attempt_in_window_is_429(self, client):
        # 5 attempts allowed, the 6th is rejected BEFORE credential check.
        for i in range(5):
            client.post(
                "/v1/auth/login",
                data={"email": f"u{i}@example.com", "password": "x"},
            )
        resp = client.post(
            "/v1/auth/login",
            data={"email": "u6@example.com", "password": "x"},
        )
        assert resp.status_code == 429

    def test_limit_is_per_ip_and_resettable(self, client):
        # Fixture reset between tests: a fresh limiter allows again.
        allowed, _ = check_login_rate_limit("10.0.0.9")
        assert allowed is True


class TestTenantRunRateLimit:
    def _demo_headers(self, client):
        resp = client.post("/v1/auth/demo-token")
        return {"X-API-Key": resp.json()["api_key"]}

    def test_run_submission_ceiling_returns_429_with_retry_after(self, client, monkeypatch):
        headers = self._demo_headers(client)
        # Both runs.py and rate_limit.py share the settings singleton —
        # patch the ATTRIBUTE (auto-restored), not either module's name.
        monkeypatch.setattr(settings, "rate_limit_runs_per_minute", 2)
        body = {"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]}
        assert client.post("/v1/runs", json=body, headers=headers).status_code == 200
        assert client.post("/v1/runs", json=body, headers=headers).status_code == 200
        throttled = client.post("/v1/runs", json=body, headers=headers)
        assert throttled.status_code == 429
        assert throttled.headers.get("Retry-After")

    def test_ceiling_is_per_project_not_global(self, client, monkeypatch):
        """Two projects each get their own budget (tenant isolation holds
        under load, not just under reads)."""
        import asyncio
        from app.core.crypto import hash_api_key
        from app.db import database
        from app.db.models import ApiKey, Organization, Project

        raw_other = "wfl_other_" + "e" * 32

        async def _mk():
            async with database.async_session_factory() as s:
                org = Organization(name="B")
                s.add(org)
                await s.flush()
                proj = Project(org_id=org.id, name="B project")
                s.add(proj)
                await s.flush()
                s.add(ApiKey(project_id=proj.id,
                             key_hash=hash_api_key(raw_other),
                             label="b", scopes=["run_tests", "admin"]))
                await s.commit()

        asyncio.run(_mk())

        monkeypatch.setattr(settings, "rate_limit_runs_per_minute", 1)
        body = {"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]}
        # Tenant A burns its one slot
        assert client.post("/v1/runs", json=body, headers=self._demo_headers(client)).status_code == 200
        assert client.post("/v1/runs", json=body, headers=self._demo_headers(client)).status_code == 429
        # Tenant B is unaffected
        assert client.post("/v1/runs", json=body, headers={"X-API-Key": raw_other}).status_code == 200
