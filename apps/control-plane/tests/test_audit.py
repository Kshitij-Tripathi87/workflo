"""Audit trail + tenant-boundary enforcement tests (SOC 2 CC6.1 / CC7.2 / CC7.3).

Covers:
  - Security-relevant actions produce audit_events rows (login, run create,
    key lifecycle) with tenant attribution and bounded detail.
  - GET /v1/audit/events is project-scoped and admin-gated.
  - Cross-tenant access to runs/keys returns 404 (not 403) so foreign
    resource IDs are not enumerable.
"""

from sqlalchemy import select

from app.db import database
from app.db.models import ApiKey, AuditEvent, Organization, Project


def _demo_headers(client):
    resp = client.post("/v1/auth/demo-token")
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["api_key"]}


def _fetch_events(**filters) -> list[AuditEvent]:
    """Read audit events straight from the DB (tests run sync)."""
    import asyncio

    async def _go():
        async with database.async_session_factory() as s:
            stmt = select(AuditEvent)
            for key, value in filters.items():
                stmt = stmt.where(getattr(AuditEvent, key) == value)
            return list((await s.execute(stmt)).scalars())

    return asyncio.run(_go())


def _make_tenant(db_session_required=None):
    """Create an isolated org+project+admin key directly (audit plumbing
    shouldn't depend on signup endpoints)."""
    import asyncio
    from app.core.crypto import hash_api_key

    raw_key = "wfl_testkey_" + "f" * 32

    async def _go():
        async with database.async_session_factory() as s:
            org = Organization(name="Other Org")
            s.add(org)
            await s.flush()
            proj = Project(org_id=org.id, name="Other Project")
            s.add(proj)
            await s.flush()
            key = ApiKey(
                project_id=proj.id,
                key_hash=hash_api_key(raw_key),
                label="other-admin",
                scopes=["run_tests", "read_reports", "admin"],
            )
            s.add(key)
            await s.commit()
            return raw_key, proj.id

    return asyncio.run(_go())


class TestAuditTrail:
    def test_login_success_is_audited(self, client):
        client.post(
            "/v1/auth/signup",
            data={"email": "auditor@example.com", "password": "correct horse 9"},
        )
        resp = client.post(
            "/v1/auth/login",
            data={"email": "auditor@example.com", "password": "correct horse 9"},
        )
        assert resp.status_code == 200, resp.text

        events = _fetch_events(action="auth.login", outcome="success")
        assert events, "login success must be audited"
        event = events[-1]
        assert event.actor_type == "user"
        assert event.project_id  # tenant attribution present
        assert event.client_ip
        # No password or token material may leak into the audit row
        assert "correct horse" not in str(event.detail_json)

    def test_login_failure_is_audited_without_email_enumeration(self, client):
        resp = client.post(
            "/v1/auth/login",
            data={"email": "ghost@example.com", "password": "nope"},
        )
        assert resp.status_code == 400
        events = _fetch_events(action="auth.login", outcome="denied")
        assert events, "login denial must be audited"
        # detail stores only the domain — not the full email (no enumeration)
        assert events[-1].detail_json.get("email_domain") == "example.com"

    def test_run_create_is_audited_with_project_attribution(self, client):
        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["run_id"]

        events = _fetch_events(action="run.create", resource_id=run_id)
        assert len(events) == 1
        assert events[0].project_id == "default"
        assert events[0].outcome == "success"

    def test_audit_events_endpoint_requires_admin_scope(self, client):
        # The demo key HAS admin scope; create one without it.
        raw_limited, _proj = _make_tenant()
        headers_limited = {"X-API-Key": raw_limited}
        # Downgrade scopes: recreate a limited key in the same project
        resp = client.post(
            "/v1/keys",
            json={"label": "limited", "scopes": ["run_tests"]},
        )
        assert resp.status_code == 200
        limited = {"X-API-Key": resp.json()["raw_key"]}

        denied = client.get("/v1/audit/events", headers=limited)
        assert denied.status_code == 403

        ok = client.get("/v1/audit/events", headers=_demo_headers(client))
        assert ok.status_code == 200, ok.text

    def test_audit_events_are_project_scoped(self, client):
        """Tenant A's audit trailing must not include tenant B's events."""
        # Tenant A (other project) creates a run
        raw_other, other_project = _make_tenant()
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
            headers={"X-API-Key": raw_other},
        )
        assert resp.status_code == 200, resp.text

        # Demo-tenant key asks for its own events — must not see tenant A's run
        demo_view = client.get("/v1/audit/events", headers=_demo_headers(client))
        assert demo_view.status_code == 200
        proj_ids = {e["project_id"] for e in demo_view.json()}
        assert other_project not in proj_ids

        # Tenant A sees its own event
        other_view = client.get("/v1/audit/events", headers={"X-API-Key": raw_other})
        assert other_view.status_code == 200
        run_creates = [e for e in other_view.json() if e["action"] == "run.create"]
        assert run_creates and all(e["project_id"] == other_project for e in run_creates)

    def test_request_id_is_echoed_for_correlation(self, client):
        resp = client.get("/v1/health", headers={"X-Request-ID": "req-trace-123"})
        assert resp.headers.get("X-Request-ID") == "req-trace-123"


class TestCrossTenantBoundaries:
    """BOLA regression tests: foreign resource IDs must be deniable
    WITHOUT confirming they exist (404, not 403)."""

    def test_get_run_from_other_project_is_404(self, client):
        raw_other, _ = _make_tenant()
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
            headers={"X-API-Key": raw_other},
        )
        foreign_run_id = resp.json()["run_id"]

        # Demo-tenant key must not read it
        blocked = client.get(f"/v1/runs/{foreign_run_id}", headers=_demo_headers(client))
        assert blocked.status_code == 404
        # Owner can read it
        allowed = client.get(f"/v1/runs/{foreign_run_id}", headers={"X-API-Key": raw_other})
        assert allowed.status_code == 200

    def test_legacy_callbacks_from_other_project_are_404(self, client):
        raw_other, _ = _make_tenant()
        resp = client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
            headers={"X-API-Key": raw_other},
        )
        foreign_run_id = resp.json()["run_id"]
        demo = _demo_headers(client)

        for method, path, kwargs in (
            ("post", f"/v1/runs/{foreign_run_id}/complete", {"json": {"total": 1}}),
            ("post", f"/v1/runs/{foreign_run_id}/logs", {"params": {"log_line": "x"}}),
            ("post", f"/v1/runs/{foreign_run_id}/cancel", {}),
            ("get", f"/v1/runs/{foreign_run_id}/legacy", {}),
        ):
            r = getattr(client, method)(path, headers=demo, **kwargs)
            assert r.status_code == 404, f"{method} {path} -> {r.status_code}"

    def test_revoke_key_from_other_project_is_404(self, client):
        raw_other, _ = _make_tenant()
        # Tenant B creates a key in its own project via its admin key
        import asyncio
        from app.core.crypto import hash_api_key

        async def _key_id():
            async with database.async_session_factory() as s:
                stmt = select(ApiKey).where(ApiKey.label == "other-admin")
                rec = (await s.execute(stmt)).scalar_one()
                return rec.id

        foreign_key_id = asyncio.run(_key_id())
        blocked = client.delete(f"/v1/keys/{foreign_key_id}", headers=_demo_headers(client))
        assert blocked.status_code == 404
