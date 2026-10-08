"""Organization export/delete tests (SOC 2 CC6.7; erasure readiness)."""


def _signup_and_login(client, email):
    client.post("/v1/auth/signup", data={"email": email, "password": "pw-123456"})
    login = client.post("/v1/auth/login", data={"email": email, "password": "pw-123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, login, token


class TestOrgExportDelete:
    def test_export_returns_own_org_only(self, client):
        headers, _login, _token = _signup_and_login(client, "exporter@example.com")
        # The login response doesn't carry the org id; resolve from the DB.
        import asyncio
        from sqlalchemy import select
        from app.db import database
        from app.db.models import Organization

        async def _org():
            async with database.async_session_factory() as s:
                return (await s.execute(
                    select(Organization).where(Organization.name == "Org for exporter@example.com")
                )).scalar_one().id

        real_org_id = asyncio.run(_org())
        resp = client.get(f"/v1/orgs/{real_org_id}/export", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["organization"]["id"] == real_org_id
        assert any(p["name"] == "Workspace for exporter@example.com" for p in body["projects"])

    def test_export_other_org_is_404(self, client):
        headers, _, _ = _signup_and_login(client, "a@example.com")
        _b_headers, _, _ = _signup_and_login(client, "b@example.com")

        import asyncio
        from sqlalchemy import select
        from app.db import database
        from app.db.models import Organization

        async def _org(name):
            async with database.async_session_factory() as s:
                return (await s.execute(
                    select(Organization).where(Organization.name == name)
                )).scalar_one().id

        org_b = asyncio.run(_org("Org for b@example.com"))
        # a's token against b's org: 404 (not enumerable)
        resp = client.get(f"/v1/orgs/{org_b}/export", headers=headers)
        assert resp.status_code == 404

    def test_delete_erases_cascade_and_is_audited(self, client):
        headers, _, _ = _signup_and_login(client, "eraseme@example.com")

        import asyncio
        from sqlalchemy import select
        from app.db import database
        from app.db.models import AuditEvent, Organization, Project, TestRun

        async def _org_id():
            async with database.async_session_factory() as s:
                return (await s.execute(
                    select(Organization).where(Organization.name == "Org for eraseme@example.com")
                )).scalar_one().id

        org_id = asyncio.run(_org_id())

        # Produce a run inside this org's project so the cascade has work
        import asyncio as _a
        from app.core.crypto import hash_api_key
        from app.db.models import ApiKey

        async def _project():
            async with database.async_session_factory() as s:
                return (await s.execute(
                    select(Project).where(Project.org_id == org_id)
                )).scalar_one().id

        proj_id = asyncio.run(_project())
        client.post(
            "/v1/runs",
            json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
            headers={"X-API-Key": _project_key(client, proj_id)},
        )

        resp = client.delete(f"/v1/orgs/{org_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] is True
        assert resp.json()["projects_deleted"] >= 1

        async def _counters():
            async with database.async_session_factory() as s:
                orgs = (await s.execute(select(Organization).where(Organization.id == org_id))).scalars().all()
                projs = (await s.execute(select(Project).where(Project.org_id == org_id))).scalars().all()
                runs = (await s.execute(select(TestRun).where(TestRun.project_id == proj_id))).scalars().all()
                audits = (await s.execute(
                    select(AuditEvent).where(AuditEvent.action == "org.delete"))
                ).scalars().all()
                return len(orgs), len(projs), len(runs), len(audits)

        orgs, projs, runs, audits = asyncio.run(_counters())
        assert orgs == 0 and projs == 0 and runs == 0
        assert audits >= 1, "erasure itself must be audited"

    def test_export_requires_bearer_auth(self, client):
        resp = client.get("/v1/orgs/any/export")
        assert resp.status_code == 401


def _demo_key(client):
    return client.post("/v1/auth/demo-token").json()["api_key"]


def _project_key(client, project_id):
    """Mint an API key scoped to a specific project (test helper)."""
    resp = client.post("/v1/keys", json={"project_id": project_id, "label": "t",
                                         "scopes": ["run_tests", "admin"]})
    assert resp.status_code == 200, resp.text
    return resp.json()["raw_key"]
