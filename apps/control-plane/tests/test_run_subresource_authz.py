"""Regression tests for object-level authorization on run sub-resources.

`GET /v1/runs/{run_id}/artifacts|results|report` used to be unauthenticated:
a run id was treated as sufficient authorization, so anyone holding or
guessing an id could read another tenant's results, assertions, captured
errors and artifact paths. These tests fail if that regression returns.
"""

import asyncio

import pytest


def _session_factory():
    """The per-test factory (conftest patches it on the module, so resolve late)."""
    from app.db import database

    return database.async_session_factory


def _create_run(project_id: str, run_id: str) -> None:
    """Insert a run belonging to `project_id` directly (no API round trip)."""

    async def _insert() -> None:
        from app.db.models import Organization, Project, TestRun

        async with _session_factory()() as session:
            if await session.get(Project, project_id) is None:
                org = Organization(name=f"org-{project_id}")
                session.add(org)
                await session.flush()
                session.add(Project(id=project_id, org_id=org.id, name=project_id))
                await session.flush()
            session.add(
                TestRun(id=run_id, project_id=project_id, goal="tests", status="completed")
            )
            await session.commit()

    asyncio.run(_insert())


def _key_for(client, project_id: str) -> dict:
    """Mint a key bound to `project_id` via the local bootstrap path."""
    resp = client.post(
        "/v1/keys",
        json={"project_id": project_id, "label": "t", "scopes": ["run_tests", "read_reports"]},
    )
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["raw_key"]}


ENDPOINTS = ("artifacts", "results", "report")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_run_subresource_requires_authentication(client, endpoint):
    _create_run("proj-a", "run-owned")
    resp = client.get(f"/v1/runs/run-owned/{endpoint}")
    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_run_subresource_rejects_foreign_tenant(client, endpoint):
    _create_run("proj-a", "run-a")
    _create_run("proj-b", "run-b")
    headers = _key_for(client, "proj-a")

    own = client.get(f"/v1/runs/run-a/{endpoint}", headers=headers)
    assert own.status_code == 200, own.text

    # Another tenant's run must be indistinguishable from a missing one.
    foreign = client.get(f"/v1/runs/run-b/{endpoint}", headers=headers)
    missing = client.get(f"/v1/runs/does-not-exist/{endpoint}", headers=headers)
    assert foreign.status_code == 404, foreign.text
    assert foreign.status_code == missing.status_code
    assert foreign.json() == missing.json()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_run_subresource_rejects_invalid_key(client, endpoint):
    _create_run("proj-a", "run-a")
    resp = client.get(
        f"/v1/runs/run-a/{endpoint}", headers={"X-API-Key": "wf_live_not-a-real-key"}
    )
    assert resp.status_code == 401


def test_anonymous_key_bootstrap_is_closed_by_default(client, monkeypatch):
    """Without the explicit opt-in, an anonymous caller cannot mint keys."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "allow_anonymous_key_bootstrap", False)
    resp = client.post("/v1/keys", json={"project_id": "victim", "label": "x"})
    assert resp.status_code == 403, resp.text
    assert "ALLOW_ANONYMOUS_KEY_BOOTSTRAP" in resp.json()["detail"]


def test_authenticated_caller_cannot_mint_a_key_for_another_project(client):
    """`project_id` in the body is ignored for authenticated callers."""
    _create_run("proj-a", "run-a")
    headers = _key_for(client, "proj-a")
    resp = client.post(
        "/v1/keys", json={"project_id": "victim", "label": "x"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_id"] == "proj-a"


def test_bearer_verification_only_considers_the_caller():
    """Token lookup is scoped by the verified `sub` claim, not the whole table."""
    from app.core.crypto import hash_token, sign_access_token, token_expiry
    from app.core.security import verify_bearer_token
    from app.db.models import OAuthToken, User

    def _token(user_id: str, tag: str) -> OAuthToken:
        return OAuthToken(
            user_id=user_id,
            client_id="cli",
            access_token_hash=hash_token(tag),
            refresh_token_hash=hash_token(f"r-{tag}"),
            access_token_expires_at=token_expiry(15),
            refresh_token_expires_at=token_expiry(15),
        )

    async def _run() -> None:
        async with _session_factory()() as session:
            alice = User(email="alice@example.com", password_hash="x")
            bob = User(email="bob@example.com", password_hash="x")
            session.add_all([alice, bob])
            await session.flush()

            token = sign_access_token({"sub": alice.id, "email": alice.email})
            session.add(_token(alice.id, token))
            for i in range(5):
                session.add(_token(bob.id, f"other-{i}"))
            await session.commit()

            row, user = await verify_bearer_token(f"Bearer {token}", session)
            assert user.id == alice.id
            assert row.user_id == alice.id

    asyncio.run(_run())
