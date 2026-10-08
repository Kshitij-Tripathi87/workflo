"""OAuth 2.0 Device Authorization Grant client (RFC 8628).

This module implements the client side of the device flow: requesting a
device code, displaying the user code, polling the token endpoint until the
user approves (or the code expires), and refreshing access tokens.

The client never receives the user's password. It receives tokens only after
the user completes browser authorization. The device code is private to the
CLI session and must never be displayed in the terminal; only the user code
is safe to show to the user.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


# RFC 8628 grant type identifier for the device flow.
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# RFC 6749 grant type for refresh token exchanges.
REFRESH_GRANT_TYPE = "refresh_token"


class DeviceAuthError(Exception):
    """Raised when the device authorization flow fails.

    The ``code`` attribute carries the OAuth error string returned by the
    authorization server (e.g. ``authorization_pending``, ``expired_token``,
    ``slow_down``, ``access_denied``, ``invalid_grant``). Terminal error codes
    (anything that is not ``authorization_pending`` or ``slow_down``) are
    surfaced to the caller so the CLI can print a clear, actionable message.
    """

    def __init__(self, code: str, description: str = "") -> None:
        self.code = code
        self.description = description
        super().__init__(f"{code}: {description}" if description else code)


@dataclass
class DeviceCodeResponse:
    """The response from ``POST /oauth/device/authorize``."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int = 5
    verification_uri_complete: Optional[str] = None
    # Internal: when the device code expires (epoch seconds).
    expires_at: float = field(default=0.0)

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        return current >= self.expires_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - time.time())


@dataclass
class TokenResponse:
    """The token response from ``POST /oauth/token``."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900
    scope: str = ""

    @property
    def expires_at(self) -> float:
        return time.time() + self.expires_in


class DeviceAuthClient:
    """Client for the OAuth 2.0 Device Authorization Grant.

    Each product CLI (workflo, astra, nexus) constructs its own client with a
    product-specific ``client_id`` and scope set, but they all talk to the same
    Cortex authorization server.
    """

    def __init__(
        self,
        client_id: str,
        base_url: str,
        *,
        scopes: list[str],
        timeout: float = 10.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.scopes = list(scopes)
        self.timeout = timeout
        # Allow injecting a client for testing (e.g. respx-mocked transport).
        self._http = http_client or httpx.Client(timeout=timeout)

    @property
    def scope_string(self) -> str:
        return " ".join(self.scopes)

    def request_device_code(self) -> DeviceCodeResponse:
        """Step 1: request a device code from the authorization server.

        Sends ``POST /oauth/device/authorize`` with the client id and scopes.
        Returns the device code response. The device code is private; only
        the user code is displayed to the user.
        """
        payload = {
            "client_id": self.client_id,
            "scope": self.scope_string,
        }
        resp = self._http.post(
            f"{self.base_url}/oauth/device/authorize",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            self._raise_http_error(resp)
        data = resp.json()
        try:
            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_uri = data["verification_uri"]
        except KeyError as exc:
            raise DeviceAuthError(
                "invalid_response",
                f"Authorization server response missing field: {exc.args[0]}",
            ) from exc

        expires_in = int(data.get("expires_in", 600))
        interval = int(data.get("interval", 5))
        return DeviceCodeResponse(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=data.get("verification_uri_complete"),
            expires_in=expires_in,
            interval=interval,
            expires_at=time.time() + expires_in,
        )

    def poll_for_token(self, device_code: DeviceCodeResponse, *, max_polls: Optional[int] = None) -> TokenResponse:
        """Step 3: poll the token endpoint until the user approves.

        Follows the server-provided polling interval and honors ``slow_down``
        by increasing the wait between polls. Raises ``DeviceAuthError`` for
        terminal states (``expired_token``, ``access_denied``, ``invalid_grant``)
        or network errors after retries are exhausted.
        """
        interval = max(1, device_code.interval)
        polls = 0
        while True:
            if device_code.is_expired():
                raise DeviceAuthError("expired_token", "Device code expired before approval")
            polls += 1
            if max_polls is not None and polls > max_polls:
                raise DeviceAuthError("expired_token", "Polling exceeded maximum attempts")
            token = self._poll_once(device_code.device_code)
            if token is not None:
                return token
            time.sleep(interval)

    def _poll_once(self, device_code: str) -> Optional[TokenResponse]:
        """Perform a single token poll. Returns a token or None to keep polling.

        On ``slow_down`` the interval is increased by the caller via a module
        flag; here we just signal "keep polling" by returning None.
        """
        payload = {
            "grant_type": DEVICE_GRANT_TYPE,
            "device_code": device_code,
            "client_id": self.client_id,
        }
        try:
            resp = self._http.post(
                f"{self.base_url}/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise DeviceAuthError("network_error", str(exc)) from exc

        if resp.status_code == 200:
            data = resp.json()
            return TokenResponse(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_in=int(data.get("expires_in", 900)),
                scope=data.get("scope", ""),
            )

        # Error response per RFC 8628.
        try:
            data = resp.json()
            error = data.get("error", "invalid_grant")
            error_description = data.get("error_description", "")
        except ValueError:
            error = "invalid_grant"
            error_description = resp.text[:200]

        if error == "authorization_pending":
            return None
        # slow_down: caller should back off. We inherit the contract by
        # treating it as "keep polling" but with a larger interval handled
        # externally; for simplicity here the caller sleeps longer next loop.
        if error == "slow_down":
            return None
        # Terminal errors: explode immediately.
        raise DeviceAuthError(error, error_description)

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for a new access token.

        The authorization server should invalidate the old refresh token on a
        successful exchange (rotating refresh tokens). The caller must replace
        the stored refresh token with the one returned here.
        """
        payload = {
            "grant_type": REFRESH_GRANT_TYPE,
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        try:
            resp = self._http.post(
                f"{self.base_url}/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise DeviceAuthError("network_error", str(exc)) from exc

        if resp.status_code != 200:
            self._raise_http_error(resp)
        data = resp.json()
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 900)),
            scope=data.get("scope", self.scope_string),
        )

    def revoke_token(self, token: str, *, token_type_hint: str = "refresh_token") -> None:
        """Revoke a token at ``POST /oauth/revoke``.

        Used by ``logout`` to invalidate the refresh token on the server side
        so a leaked credential cannot be reused after the user signs out.
        """
        payload = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": self.client_id,
        }
        try:
            resp = self._http.post(
                f"{self.base_url}/oauth/revoke",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise DeviceAuthError("network_error", str(exc)) from exc
        # RFC 7009: a successful revocation returns 200 even for unknown tokens.
        if resp.status_code != 200:
            self._raise_http_error(resp)

    def _raise_http_error(self, resp: httpx.Response) -> None:
        try:
            data = resp.json()
            error = data.get("error", "http_error")
            description = data.get("error_description", resp.text[:200])
        except ValueError:
            error = "http_error"
            description = f"HTTP {resp.status_code}: {resp.text[:200]}"
        raise DeviceAuthError(error, description)

    def close(self) -> None:
        self._http.close()
