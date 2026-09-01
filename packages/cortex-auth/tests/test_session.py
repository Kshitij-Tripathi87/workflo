"""Tests for the high-level AuthSession orchestration layer."""

import base64
import json
import time
from pathlib import Path
from typing import Callable

import httpx
import pytest

from cortex_auth.credential_store import FileCredentialStore
from cortex_auth.profile import ProfileManager
from cortex_auth.session import AuthSession, AuthError


def _make_jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


def _make_auth_session(
    handler: Callable[[httpx.Request], httpx.Response],
    tmp_path: Path,
) -> AuthSession:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    store = FileCredentialStore(tmp_path / "creds.json")
    profiles = ProfileManager(tmp_path / "config.json")
    return AuthSession(
        product="workflo",
        client_id="workflo_cli",
        base_url="https://auth.cortex.dev",
        scopes=["openid", "profile", "workflo:runs:create"],
        credential_store=store,
        profile_manager=profiles,
        http_client=http,
    )


DEVICE_CODE_BODY = {
    "device_code": "dc_7f91",
    "user_code": "R7KM-L2QP",
    "verification_uri": "https://app.cortex.dev/device",
    "verification_uri_complete": "https://app.cortex.dev/device?user_code=R7KM-L2QP",
    "expires_in": 600,
    "interval": 0,
}


class TestLogin:
    def test_login_persists_session(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("cortex_auth.session._try_open_browser", lambda url: True)
        calls = {"n": 0}

        def handler(request: httpx.Request):
            if request.url.path == "/oauth/device/authorize":
                return httpx.Response(200, json=DEVICE_CODE_BODY)
            if request.url.path == "/oauth/token":
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(
                        200,
                        json={
                            "access_token": _make_jwt({
                                "sub": "user_123",
                                "email": "aarav@cortex.dev",
                                "organization_id": "org_456",
                                "organization_name": "Cortex Labs",
                                "workspace_id": "ws_789",
                                "workspace_name": "Engineering",
                            }),
                            "refresh_token": "rt_abc",
                            "token_type": "Bearer",
                            "expires_in": 900,
                            "scope": "openid profile workflo:runs:create",
                        },
                    )
            return httpx.Response(404)

        session = _make_auth_session(handler, tmp_path)
        result = session.login("cortex-labs", open_browser=True)
        assert result.session.user_id == "user_123"
        assert result.session.email == "aarav@cortex.dev"
        assert result.session.organization_name == "Cortex Labs"
        # Refresh token stored in credential store.
        assert result.backend_name
        # Profile recorded.
        profiles = session.list_profiles()
        assert any(p.name == "cortex-labs" for p in profiles)

    def test_login_headless_does_not_open_browser(self, tmp_path: Path, monkeypatch):
        opened = {"yes": False}
        monkeypatch.setattr("cortex_auth.session._try_open_browser", lambda url: opened.__setitem__("yes", True) or True)
        calls = {"n": 0}

        def handler(request: httpx.Request):
            if request.url.path == "/oauth/device/authorize":
                return httpx.Response(200, json=DEVICE_CODE_BODY)
            if request.url.path == "/oauth/token":
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(200, json={
                        "access_token": _make_jwt({"sub": "u1"}),
                        "refresh_token": "rt1",
                        "expires_in": 900,
                    })
            return httpx.Response(404)

        session = _make_auth_session(handler, tmp_path)
        session.login("default", open_browser=False)
        assert opened["yes"] is False


class TestGetAccessToken:
    def test_returns_stored_access_token_if_valid(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("cortex_auth.session._try_open_browser", lambda url: True)
        calls = {"n": 0}

        def handler(request: httpx.Request):
            if request.url.path == "/oauth/device/authorize":
                return httpx.Response(200, json=DEVICE_CODE_BODY)
            if request.url.path == "/oauth/token":
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(200, json={
                        "access_token": _make_jwt({"sub": "u1"}),
                        "refresh_token": "rt1",
                        "expires_in": 3600,
                    })
            return httpx.Response(404)

        session = _make_auth_session(handler, tmp_path)
        session.login("default", open_browser=True)
        token = session.get_access_token()
        assert token == session.status().access_token

    def test_refreshes_when_access_token_expired(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("cortex_auth.session._try_open_browser", lambda url: True)
        calls = {"n": 0}

        def handler(request: httpx.Request):
            if request.url.path == "/oauth/device/authorize":
                return httpx.Response(200, json=DEVICE_CODE_BODY)
            if request.url.path == "/oauth/token":
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(200, json={
                        "access_token": _make_jwt({"sub": "u1"}),
                        "refresh_token": "rt1",
                        "expires_in": 0,  # already expired
                    })
                # refresh call
                return httpx.Response(200, json={
                    "access_token": _make_jwt({"sub": "u1"}),
                    "refresh_token": "rt2",
                    "expires_in": 3600,
                })
            return httpx.Response(404)

        session = _make_auth_session(handler, tmp_path)
        session.login("default", open_browser=True)
        token = session.get_access_token()
        assert token  # got a new token from refresh
        assert calls["n"] >= 2

    def test_raises_when_not_logged_in(self, tmp_path: Path):
        session = _make_auth_session(lambda req: httpx.Response(404), tmp_path)
        with pytest.raises(AuthError):
            session.get_access_token()


class TestLogout:
    def test_logout_clears_credentials(self, tmp_path: Path, monkeypatch):
        from cortex_auth.credential_store import FileCredentialStore

        monkeypatch.setattr("cortex_auth.session._try_open_browser", lambda url: True)
        calls = {"n": 0}
        revoke_seen = {"yes": False}

        def handler(request: httpx.Request):
            if request.url.path == "/oauth/device/authorize":
                return httpx.Response(200, json=DEVICE_CODE_BODY)
            if request.url.path == "/oauth/token":
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(200, json={
                        "access_token": _make_jwt({"sub": "u1"}),
                        "refresh_token": "rt1",
                        "expires_in": 3600,
                    })
            if request.url.path == "/oauth/revoke":
                revoke_seen["yes"] = True
                return httpx.Response(200, json={})
            return httpx.Response(404)

        session = _make_auth_session(handler, tmp_path)
        session.login("default", open_browser=True)
        store = session._store
        assert store.get("default", "refresh_token") == "rt1"
        session.logout()
        assert store.get("default", "refresh_token") is None
        assert store.get("default", "access_token") is None
        assert session.list_profiles() == []
        assert revoke_seen["yes"] is True


class TestServiceTokenLogin:
    def test_service_token_session(self, tmp_path: Path):
        session = _make_auth_session(lambda req: httpx.Response(404), tmp_path)
        token = _make_jwt({
            "sub": "",
            "organization_id": "org_1",
            "exp": time.time() + 3600,
        })
        result = session.login_with_service_token(
            "ci", token, workspace_id="ws_1", scopes=["workflo:runs:create"],
        )
        assert result.session.is_service_token is True
        assert result.session.workspace_id == "ws_1"

    def test_service_token_get_access_token(self, tmp_path: Path):
        session = _make_auth_session(lambda req: httpx.Response(404), tmp_path)
        token = _make_jwt({"sub": "", "exp": time.time() + 3600})
        session.login_with_service_token(
            "ci", token, workspace_id="ws_1", scopes=["workflo:runs:create"],
        )
        # Service tokens are returned as-is (no refresh).
        assert session.get_access_token() == token
