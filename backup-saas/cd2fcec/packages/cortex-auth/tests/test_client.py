"""Tests for the OAuth 2.0 Device Authorization Grant client (RFC 8628).

Uses httpx's MockTransport to simulate the authorization server without
network or external mocking libraries.
"""

import json
import time
from typing import Callable

import httpx
import pytest

from cortex_auth.client import (
    DeviceAuthClient,
    DeviceAuthError,
    DEVICE_GRANT_TYPE,
)


def _make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> DeviceAuthClient:
    transport = httpx.MockTransport(handler)
    transport = transport
    http = httpx.Client(transport=transport)
    return DeviceAuthClient(
        client_id="workflo_cli",
        base_url="https://auth.cortex.dev",
        scopes=["openid", "profile", "workflo:runs:create"],
        http_client=http,
    )


DEVICE_CODE_BODY = {
    "device_code": "dc_7f91",
    "user_code": "R7KM-L2QP",
    "verification_uri": "https://app.cortex.dev/device",
    "verification_uri_complete": "https://app.cortex.dev/device?user_code=R7KM-L2QP",
    "expires_in": 600,
    "interval": 1,
}


TOKEN_BODY = {
    "access_token": "at_abc",
    "refresh_token": "rt_abc",
    "token_type": "Bearer",
    "expires_in": 900,
    "scope": "openid profile workflo:runs:create",
}


class TestRequestDeviceCode:
    def test_returns_parsed_response(self):
        def handler(request: httpx.Request):
            assert request.url.path == "/oauth/device/authorize"
            assert "client_id=workflo_cli" in request.content.decode()
            return httpx.Response(200, json=DEVICE_CODE_BODY)

        client = _make_client(handler)
        resp = client.request_device_code()
        assert resp.device_code == "dc_7f91"
        assert resp.user_code == "R7KM-L2QP"
        assert resp.interval == 1
        assert resp.verification_uri == "https://app.cortex.dev/device"
        assert resp.expires_in == 600

    def test_missing_field_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"device_code": "dc_x", "user_code": "AB"})

        client = _make_client(handler)
        with pytest.raises(DeviceAuthError) as exc:
            client.request_device_code()
        assert exc.value.code == "invalid_response"

    def test_server_error_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, json={"error": "server_error", "error_description": "boom"})

        client = _make_client(handler)
        with pytest.raises(DeviceAuthError) as exc:
            client.request_device_code()
        assert exc.value.code == "server_error"


class TestPollForToken:
    def test_pending_then_approved(self):
        """First poll returns authorization_pending, second returns a token."""
        calls = {"n": 0}

        def handler(request: httpx.Request):
            assert request.url.path == "/oauth/token"
            body = request.content.decode()
            # httpx URL-encodes colons in the form body; decode for the check.
            import urllib.parse

            fields = dict(urllib.parse.parse_qsl(body))
            assert fields["grant_type"] == DEVICE_GRANT_TYPE
            assert "device_code" in fields
            assert fields["device_code"] == "dc_7f91"
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(400, json={"error": "authorization_pending"})
            return httpx.Response(200, json=TOKEN_BODY)

        client = _make_client(handler)
        from cortex_auth.client import DeviceCodeResponse

        device_code = DeviceCodeResponse(
            device_code="dc_7f91",
            user_code="R7KM-L2QP",
            verification_uri="https://app.cortex.dev/device",
            expires_in=600,
            interval=0,  # do not actually sleep
            expires_at=time.time() + 600,
        )
        token = client.poll_for_token(device_code, max_polls=5)
        assert token.access_token == "at_abc"
        assert token.refresh_token == "rt_abc"
        assert calls["n"] == 2

    def test_slow_down_keeps_polling(self):
        calls = {"n": 0}

        def handler(request: httpx.Request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(400, json={"error": "slow_down"})
            return httpx.Response(200, json=TOKEN_BODY)

        client = _make_client(handler)
        from cortex_auth.client import DeviceCodeResponse

        device_code = DeviceCodeResponse(
            device_code="dc_7f91",
            user_code="R7KM-L2QP",
            verification_uri="https://app.cortex.dev/device",
            expires_in=600,
            interval=0,
            expires_at=time.time() + 600,
        )
        token = client.poll_for_token(device_code, max_polls=5)
        assert token.access_token == "at_abc"

    def test_access_denied_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(400, json={"error": "access_denied"})

        client = _make_client(handler)
        from cortex_auth.client import DeviceCodeResponse

        device_code = DeviceCodeResponse(
            device_code="dc_7f91",
            user_code="R7KM-L2QP",
            verification_uri="https://app.cortex.dev/device",
            expires_in=600,
            interval=0,
            expires_at=time.time() + 600,
        )
        with pytest.raises(DeviceAuthError) as exc:
            client.poll_for_token(device_code, max_polls=5)
        assert exc.value.code == "access_denied"

    def test_expired_code_raises(self):
        client = _make_client(lambda req: httpx.Response(400, json={"error": "authorization_pending"}))
        from cortex_auth.client import DeviceCodeResponse

        device_code = DeviceCodeResponse(
            device_code="dc_7f91",
            user_code="R7KM-L2QP",
            verification_uri="https://app.cortex.dev/device",
            expires_in=600,
            interval=0,
            expires_at=time.time() - 1,  # already expired
        )
        with pytest.raises(DeviceAuthError) as exc:
            client.poll_for_token(device_code, max_polls=5)
        assert exc.value.code == "expired_token"


class TestRefreshToken:
    def test_refresh_returns_new_token(self):
        captured = {}

        def handler(request: httpx.Request):
            assert request.url.path == "/oauth/token"
            body = request.content.decode()
            captured["body"] = body
            return httpx.Response(200, json={
                "access_token": "at_new",
                "refresh_token": "rt_new",
                "token_type": "Bearer",
                "expires_in": 900,
            })

        client = _make_client(handler)
        token = client.refresh_token("rt_old")
        assert token.access_token == "at_new"
        assert token.refresh_token == "rt_new"
        assert "refresh_token=rt_old" in captured["body"]
        assert "grant_type=refresh_token" in captured["body"]


class TestRevokeToken:
    def test_revoke_succeeds_on_200(self):
        def handler(request: httpx.Request):
            assert request.url.path == "/oauth/revoke"
            return httpx.Response(200, json={})

        client = _make_client(handler)
        client.revoke_token("rt_old")  # must not raise

    def test_revoke_raises_on_error(self):
        def handler(request: httpx.Request):
            return httpx.Response(400, json={"error": "invalid_request"})

        client = _make_client(handler)
        with pytest.raises(DeviceAuthError) as exc:
            client.revoke_token("rt_old")
        assert exc.value.code == "invalid_request"


class TestNetworkErrors:
    def test_request_device_code_network_error(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("connection refused")

        client = _make_client(handler)
        with pytest.raises((DeviceAuthError, httpx.HTTPError)):
            client.request_device_code()
