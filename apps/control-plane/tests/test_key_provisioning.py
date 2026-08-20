"""Tests for key provisioning endpoints (receipt provenance)."""

import asyncio
import base64
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.crypto import (
    hash_token,
    sign_access_token,
    token_expiry,
    refresh_token_expiry,
)
from app.db.models import OAuthToken, User, Organization, Project


def _run(coro):
    """Run an async coroutine in a sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _generate_ed25519_keypair():
    """Generate a real Ed25519 keypair for testing."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_pem


async def _seed_oauth_token(db_session_factory, user_id=None, email=None):
    """Seed a real user + JWT access token directly in the DB for testing.

    Identity binding: the access token is a signed JWT whose claims match a
    REAL user row (verify_bearer_token loads the user by the token record's
    user_id), so the fixture must create the User too.
    """
    suffix = uuid.uuid4().hex[:8]
    resolved_user_id = user_id or f"user-{suffix}"
    async with db_session_factory() as db:
        org = Organization(name=f"Org {suffix}")
        db.add(org)
        await db.flush()
        user = User(
            id=resolved_user_id,
            email=email or f"user-{suffix}@example.com",
            password_hash="unused-in-fixture",
            org_id=org.id,
        )
        db.add(user)
        await db.flush()
        project = Project(org_id=org.id, name=f"Workspace {suffix}")
        db.add(project)
        await db.flush()
        user.project_id = project.id

        scopes = ["workflo:runs:create", "workflo:receipts:read"]
        raw_access = sign_access_token(
            {
                "sub": user.id,
                "email": user.email,
                "client_id": "workflo_cli",
                "organization_id": org.id,
                "organization_name": org.name,
                "workspace_id": project.id,
                "workspace_name": project.name,
                "scopes": scopes,
                "iss": "cortex-control-plane",
            }
        )
        raw_refresh = "wfl_rt_test_" + base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("=")
        token = OAuthToken(
            user_id=user.id,
            client_id="workflo_cli",
            organization_id=org.id,
            workspace_id=project.id,
            scopes=scopes,
            access_token_hash=hash_token(raw_access),
            refresh_token_hash=hash_token(raw_refresh),
            access_token_expires_at=token_expiry(15),
            refresh_token_expires_at=refresh_token_expiry(30),
        )
        db.add(token)
        await db.commit()
    return raw_access


def test_provision_requires_auth(client):
    """POST /provision without Authorization header returns 401."""
    _, public_pem = _generate_ed25519_keypair()
    resp = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-1"},
    )
    assert resp.status_code == 401


def test_provision_with_invalid_token_returns_401(client):
    """POST /provision with bad Bearer token returns 401."""
    _, public_pem = _generate_ed25519_keypair()
    resp = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-1"},
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert resp.status_code == 401


def test_provision_with_valid_token_creates_key(client):
    """POST /provision with valid Bearer token creates a ProvisionedKey."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    resp = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-alice-laptop"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "key_id" in data
    assert "fingerprint" in data
    assert data["device_id"] == "dev-alice-laptop"
    assert len(data["fingerprint"]) == 64  # SHA-256 hex


def test_provision_rejects_non_ed25519_key(client):
    """POST /provision with a non-Ed25519 key returns 400."""
    from app.db import database
    from cryptography.hazmat.primitives.asymmetric import rsa

    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pem = rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    resp = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": rsa_pem, "device_id": "dev-1"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    assert resp.status_code == 400


def test_provision_rejects_invalid_pem(client):
    """POST /provision with garbage PEM returns 400."""
    from app.db import database

    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    resp = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": "not a PEM key", "device_id": "dev-1"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    assert resp.status_code == 400


def test_provision_is_idempotent_for_same_device(client):
    """POST /provision twice with same public_key + device_id returns same key_id."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    headers = {"Authorization": f"Bearer {raw_access}"}
    body = {"public_key": public_pem, "device_id": "dev-alice"}

    resp1 = client.post("/v1/auth/keys/provision", json=body, headers=headers)
    resp2 = client.post("/v1/auth/keys/provision", json=body, headers=headers)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["key_id"] == resp2.json()["key_id"]


def test_provision_rejects_revoked_key_reuse(client):
    """Revoked key cannot be re-provisioned."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    headers = {"Authorization": f"Bearer {raw_access}"}
    body = {"public_key": public_pem, "device_id": "dev-alice"}

    resp1 = client.post("/v1/auth/keys/provision", json=body, headers=headers)
    key_id = resp1.json()["key_id"]

    resp_revoke = client.post(
        f"/v1/auth/keys/{key_id}/revoke", headers=headers
    )
    assert resp_revoke.status_code == 200

    resp2 = client.post("/v1/auth/keys/provision", json=body, headers=headers)
    assert resp2.status_code == 409


def test_get_key_returns_public_info_without_auth(client):
    """GET /{key_id} is public — no auth needed."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    provision = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-alice"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    key_id = provision.json()["key_id"]

    resp = client.get(f"/v1/auth/keys/{key_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key_id"] == key_id
    assert data["public_key"] == public_pem
    assert data["status"] == "active"


def test_get_key_404_for_unknown_key_id(client):
    """GET /{key_id} with unknown key_id returns 404."""
    resp = client.get("/v1/auth/keys/nonexistent-key-id")
    assert resp.status_code == 404


def test_revoke_key_marks_status_revoked(client):
    """POST /{key_id}/revoke flips status to revoked."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory, user_id="user-alice"))

    provision = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-alice"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    key_id = provision.json()["key_id"]

    resp = client.post(
        f"/v1/auth/keys/{key_id}/revoke",
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True

    get_resp = client.get(f"/v1/auth/keys/{key_id}")
    assert get_resp.json()["status"] == "revoked"
    assert get_resp.json()["revoked_at"] is not None


def test_revoke_requires_auth(client):
    """POST /{key_id}/revoke without auth returns 401."""
    resp = client.post("/v1/auth/keys/some-id/revoke")
    assert resp.status_code == 401


def test_revoke_other_users_key_returns_403(client):
    """Cannot revoke a key provisioned by a different user."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()

    alice_token = _run(_seed_oauth_token(database.async_session_factory, user_id="user-alice"))
    provision = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-alice"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    key_id = provision.json()["key_id"]

    bob_token = _run(_seed_oauth_token(database.async_session_factory, user_id="user-bob"))
    resp = client.post(
        f"/v1/auth/keys/{key_id}/revoke",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert resp.status_code == 403


def test_revoke_already_revoked_is_idempotent(client):
    """Revoking an already-revoked key returns revoked=False."""
    from app.db import database

    _, public_pem = _generate_ed25519_keypair()
    raw_access = _run(_seed_oauth_token(database.async_session_factory))

    provision = client.post(
        "/v1/auth/keys/provision",
        json={"public_key": public_pem, "device_id": "dev-alice"},
        headers={"Authorization": f"Bearer {raw_access}"},
    )
    key_id = provision.json()["key_id"]
    headers = {"Authorization": f"Bearer {raw_access}"}

    resp1 = client.post(f"/v1/auth/keys/{key_id}/revoke", headers=headers)
    resp2 = client.post(f"/v1/auth/keys/{key_id}/revoke", headers=headers)
    assert resp1.json()["revoked"] is True
    assert resp2.json()["revoked"] is False
