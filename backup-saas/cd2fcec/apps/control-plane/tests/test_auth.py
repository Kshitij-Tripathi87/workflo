"""Tests for API key authentication and key management."""


def test_create_key_returns_raw_key(client):
    resp = client.post("/v1/keys", json={"label": "test", "scopes": ["run_tests"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_key"].startswith("ts_live_")
    assert data["label"] == "test"
    assert "run_tests" in data["scopes"]
    assert "id" in data


def test_list_keys_requires_auth(client):
    resp = client.get("/v1/keys")
    assert resp.status_code == 401


def test_list_keys_with_auth(client):
    create = client.post("/v1/keys", json={"label": "my-key", "scopes": ["run_tests", "read_reports", "admin"]})
    raw_key = create.json()["raw_key"]
    headers = {"X-TenantShield-Key": raw_key}

    resp = client.get("/v1/keys", headers=headers)
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    assert any(k["label"] == "my-key" for k in keys)


def test_invalid_api_key_rejected(client):
    headers = {"X-TenantShield-Key": "ts_live_invalid_key_12345"}
    resp = client.get("/v1/keys", headers=headers)
    assert resp.status_code == 401


def test_revoke_key(client):
    create = client.post("/v1/keys", json={"scopes": ["run_tests", "read_reports", "admin"]})
    key_id = create.json()["id"]
    raw_key = create.json()["raw_key"]
    headers = {"X-TenantShield-Key": raw_key}

    # Revoke
    resp = client.delete(f"/v1/keys/{key_id}", headers=headers)
    assert resp.status_code == 200

    # Now the key should no longer work
    resp = client.get("/v1/keys", headers=headers)
    assert resp.status_code == 401


def test_run_with_key_has_scope(client):
    create = client.post("/v1/keys", json={"scopes": ["run_tests", "read_reports", "admin"]})
    raw_key = create.json()["raw_key"]
    headers = {"X-TenantShield-Key": raw_key}

    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
        headers=headers,
    )
    assert resp.status_code == 200


def test_key_hash_is_secure(client):
    """Verify the API key is stored as a hash, not plaintext."""
    from app.db.database import async_session_factory
    from app.db.models import ApiKey
    from sqlalchemy import select
    import asyncio

    create = client.post("/v1/keys", json={"scopes": ["run_tests"]})
    raw_key = create.json()["raw_key"]

    async def _check():
        async with async_session_factory() as session:
            stmt = select(ApiKey)
            result = await session.execute(stmt)
            for record in result.scalars():
                # Hash should NOT contain the raw key
                assert raw_key not in record.key_hash
                # Hash should contain the salt:dk format
                assert ":" in record.key_hash
    
    asyncio.run(_check())
