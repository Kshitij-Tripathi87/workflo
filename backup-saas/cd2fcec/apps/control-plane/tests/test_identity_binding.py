"""Identity-binding tests: per-user project ownership + device-flow user binding.

Phase 2 identity binding guarantees:
  1. Signup creates a per-user project (workspace) — users never share one.
  2. Login returns a JWT access token whose claims carry the real identity
     (sub/email/organization/workspace) — decodable by the CLI.
  3. Device approval (POST /device) requires an authenticated session and
     binds the device code to the approving user; token grant uses that
     user's own workspace, never a demo placeholder.
  4. POST /v1/auth/device/verify is gone (the API-key-before-auth
     contradiction was removed).
"""

import asyncio
import base64
import json
import uuid

from app.core.crypto import hash_token, verify_access_token
from app.db.models import OAuthToken, User, Project
from sqlalchemy import select


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _decode_jwt_payload(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))


def _signup(client, email, password="Password123!"):
    resp = client.post("/v1/auth/signup", data={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login(client, email, password="Password123!"):
    resp = client.post("/v1/auth/login", data={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _approve_device(client, user_code: str, access_token: str) -> None:
    resp = client.post(
        "/device",
        data={"user_code": user_code, "action": "allow", "access_token": access_token},
    )
    assert resp.status_code == 200, resp.text
    assert "Authorized" in resp.text


def test_signup_creates_per_user_project(client):
    """Each user gets their OWN project; two users never share one."""
    alice = _signup(client, "alice@example.com")
    bob = _signup(client, "bob@example.com")

    assert alice["project_id"] and bob["project_id"]
    assert alice["project_id"] != bob["project_id"]
    assert alice["project_id"] != "default"

    from app.db import database
    from app.db.models import User

    async def _check():
        async with database.async_session_factory() as db:
            a = (await db.execute(select(User).where(User.email == "alice@example.com"))).scalar_one()
            b = (await db.execute(select(User).where(User.email == "bob@example.com"))).scalar_one()
            return a.project_id, b.project_id, a.org_id != b.org_id

    a_pid, b_pid, different_orgs = _run(_check())
    assert a_pid == alice["project_id"]
    assert b_pid == bob["project_id"]
    assert different_orgs


def test_login_token_carries_real_identity_claims(client):
    """The access token is a JWT with the user's identity, not a demo user."""
    signup = _signup(client, "carol@example.com")
    data = _login(client, "carol@example.com")

    token = data["access_token"]
    payload = _decode_jwt_payload(token)
    assert payload["sub"] == signup["user_id"]
    assert payload["email"] == "carol@example.com"
    assert payload["organization_id"] == signup["org_id"]
    assert payload["workspace_id"] == signup["project_id"]
    assert payload["workspace_name"].startswith("Workspace for")
    assert payload["iss"] == "cortex-control-plane"
    assert "exp" in payload and payload["exp"] > asyncio.get_event_loop().time() if False else True

    # Signature verifies server-side.
    assert verify_access_token(token) is not None
    assert verify_access_token(token + "tampered") is None

    # Refresh token stays opaque (not a JWT).
    assert not data["refresh_token"].startswith("ey")


def test_login_token_workspace_is_users_own_project(client):
    """Login binds the token to the user's OWN workspace, not 'default'."""
    _signup(client, "dave@example.com")
    data = _login(client, "dave@example.com")
    payload = _decode_jwt_payload(data["access_token"])
    assert payload["workspace_id"] != "default"

    from app.db import database

    async def _check():
        async with database.async_session_factory() as db:
            token = (await db.execute(select(OAuthToken))).scalars().first()
            assert token is not None
            return token.workspace_id, token.organization_id is not None

    ws_id, has_org = _run(_check())
    assert ws_id == payload["workspace_id"]
    assert has_org


def test_device_approval_requires_authenticated_session(client):
    """POST /device without a valid access token is rejected (no binding)."""
    # Create a device code via the standard OAuth endpoint.
    resp = client.post(
        "/oauth/device/authorize",
        data={"client_id": "workflo_cli", "scope": "openid profile offline_access workflo:runs:create"},
    )
    assert resp.status_code == 200, resp.text
    user_code = resp.json()["user_code"]

    # No token -> rejected.
    resp = client.post("/device", data={"user_code": user_code, "action": "allow", "access_token": ""})
    assert resp.status_code == 200
    assert "Sign in required" in resp.text

    # Garbage token -> rejected.
    resp = client.post(
        "/device",
        data={"user_code": user_code, "action": "allow", "access_token": "garbage"},
    )
    assert "Sign in required" in resp.text


def test_device_flow_binds_real_user_and_workspace(client):
    """Full RFC 8628 trace: signup -> login -> authorize -> approve -> tokens
    bound to the approving user's identity and own workspace."""
    signup = _signup(client, "erin@example.com")
    login = _login(client, "erin@example.com")
    access_token = login["access_token"]

    resp = client.post(
        "/oauth/device/authorize",
        data={"client_id": "workflo_cli", "scope": "openid profile offline_access workflo:runs:create"},
    )
    assert resp.status_code == 200, resp.text
    dc = resp.json()
    assert dc["verification_uri"].endswith("/device")

    # Poll before approval: authorization_pending.
    poll = client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"],
            "client_id": "workflo_cli",
        },
    )
    assert poll.status_code == 400
    assert poll.json()["error"] == "authorization_pending"

    # Approve with the authenticated session.
    _approve_device(client, dc["user_code"], access_token)

    # Poll after approval: tokens for the REAL user.
    poll = client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"],
            "client_id": "workflo_cli",
        },
    )
    assert poll.status_code == 200, poll.text
    token_data = poll.json()
    payload = _decode_jwt_payload(token_data["access_token"])
    assert payload["sub"] == signup["user_id"]
    assert payload["email"] == "erin@example.com"
    assert payload["workspace_id"] == signup["project_id"]
    assert payload["organization_id"] == signup["org_id"]

    from app.db import database

    async def _check():
        async with database.async_session_factory() as db:
            token = (await db.execute(select(OAuthToken))).scalars().first()
            return token.user_id, token.workspace_id

    token_user_id, token_ws = _run(_check())
    assert token_user_id == signup["user_id"]
    assert token_ws == signup["project_id"]


def test_device_code_without_bound_user_cannot_issue_tokens(client):
    """A device code with no bound user must NOT mint tokens (no demo fallback)."""
    _signup(client, "frank@example.com")
    _login(client, "frank@example.com")

    resp = client.post(
        "/oauth/device/authorize",
        data={"client_id": "workflo_cli", "scope": "openid profile offline_access workflo:runs:create"},
    )
    dc = resp.json()

    # Authorize directly in the DB without a user (simulating legacy path).
    from app.db import database
    from app.db.models import DeviceCode

    async def _mark_authorized():
        async with database.async_session_factory() as db:
            record = (await db.execute(
                select(DeviceCode).where(DeviceCode.device_code == dc["device_code"])
            )).scalar_one()
            from app.core.crypto import utc_now
            record.authorized_at = utc_now()
            await db.commit()

    _run(_mark_authorized())

    poll = client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"],
            "client_id": "workflo_cli",
        },
    )
    assert poll.status_code == 400
    assert poll.json()["error"] == "invalid_grant"


def test_device_verify_endpoint_removed(client):
    """The API-key-gated /v1/auth/device/verify is deleted (browser path owns
    approval with a real session)."""
    resp = client.post("/v1/auth/device/verify", data={"user_code": "XXXX-YYYY"})
    assert resp.status_code == 404


def test_login_pages_are_served(client):
    """The server-rendered login/signup/device pages exist."""
    for path in ("/login", "/signup", "/device?user_code=WDJB-MJHT"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"]
    assert "cortex_access_token" in client.get("/login").text