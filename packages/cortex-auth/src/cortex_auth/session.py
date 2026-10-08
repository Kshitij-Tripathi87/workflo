"""High-level auth session orchestration for the Cortex CLI.

``AuthSession`` glues together the OAuth device flow client, the credential
store, and the profile manager. The CLI layer (``workflo login``,
``workflo auth status``, ...) calls into this module rather than touching the
lower-level pieces directly.

Design notes:
- Local-first. Authentication is optional for purely local execution. Cloud
  features require an explicit opt-in (``--publish``) and a stored session.
- Installation and authorization remain separate. Installing the CLI does
  not imply tenancy; the authenticated browser session selects the
  organization and workspace, and the backend enforces that choice on every
  request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from cortex_auth.client import DeviceAuthClient, DeviceAuthError, DeviceCodeResponse, TokenResponse
from cortex_auth.credential_store import CredentialStore, get_credential_store
from cortex_auth.profile import AuthProfile, ProfileError, ProfileManager, SessionInfo


# Keys used inside the credential store namespace.
REFRESH_TOKEN_KEY = "refresh_token"
ACCESS_TOKEN_KEY = "access_token"
ACCESS_TOKEN_EXPIRES_AT_KEY = "access_token_expires_at"


@dataclass
class LoginResult:
    profile: AuthProfile
    session: SessionInfo
    backend_name: str


class AuthSession:
    """Orchestrates the full device login flow for a product CLI.

    Parameters mirror the per-product conventions from the plan:
    ``product`` is the Cortex product (workflo, astra, nexus); ``client_id``
    is product-specific (e.g. ``workflo_cli``); ``scopes`` are product-
    specific scopes granted during device authorization.
    """

    def __init__(
        self,
        product: str,
        client_id: str,
        base_url: str,
        scopes: list[str],
        *,
        credential_store: Optional[CredentialStore] = None,
        profile_manager: Optional[ProfileManager] = None,
        http_client=None,
    ) -> None:
        self.product = product
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.scopes = list(scopes)
        self._store = credential_store or get_credential_store()
        self._profiles = profile_manager or ProfileManager()
        self._client = DeviceAuthClient(
            client_id=client_id,
            base_url=base_url,
            scopes=scopes,
            http_client=http_client,
        )

    # ---- Login --------------------------------------------------------

    def login(
        self,
        profile_name: str,
        *,
        open_browser: bool = True,
        poll_callback: Optional[Callable[[DeviceCodeResponse], None]] = None,
    ) -> LoginResult:
        """Run the full device flow and persist the resulting session.

        ``poll_callback`` is invoked once per poll with the device-code
        response, so the CLI can print "Still waiting for approval..." style
        messages. The callback is informational only.
        """
        device_code = self._client.request_device_code()
        if open_browser:
            _try_open_browser(device_code.verification_uri_complete or device_code.verification_uri)
        # Persist the profile definition (no secrets yet).
        profile = AuthProfile(
            name=profile_name,
            product=self.product,
            client_id=self.client_id,
            base_url=self.base_url,
            scopes=self.scopes,
        )
        self._profiles.add_profile(profile)

        token = self._client.poll_for_token(device_code)
        # Decode the access token claims without verifying signature here —
        # the authorization server signed it; verification happens server-side
        # on every API call. We only need the claims for display.
        claims = _decode_jwt_claims(token.access_token)
        session = SessionInfo(
            user_id=claims.get("sub", ""),
            email=claims.get("email", ""),
            organization_id=claims.get("organization_id", ""),
            organization_name=claims.get("organization_name", ""),
            workspace_id=claims.get("workspace_id", ""),
            workspace_name=claims.get("workspace_name", ""),
            product=self.product,
            scopes=token.scope.split() if token.scope else list(self.scopes),
            access_token=token.access_token,
            access_token_expires_at=token.expires_at,
        )
        for key, value in (
            ("user_id", session.user_id),
            ("email", session.email),
            ("organization_name", session.organization_name),
            ("workspace_name", session.workspace_name),
        ):
            if value:
                self._profiles.update_profile(profile_name, **{key: value})
        if session.organization_id:
            self._profiles.set_active_org(profile_name, session.organization_id, session.organization_name)
        if session.workspace_id:
            self._profiles.set_active_workspace(profile_name, session.workspace_id, session.workspace_name)

        self._store_access_token(profile_name, token)
        self._store_refresh_token(profile_name, token.refresh_token)
        self._profiles.set_active_profile(profile_name)

        return LoginResult(profile=profile, session=session, backend_name=self._store.backend_name())

    def login_with_service_token(self, profile_name: str, token: str, *, workspace_id: str, scopes: list[str]) -> LoginResult:
        """Create a session from a pre-existing service token (CI/CD).

        Service tokens are workspace-scoped and expiration-bound; they bypass
        the device flow entirely. The token is treated as an access token and
        stored in the credential store, never in the config file.
        """
        claims = _decode_jwt_claims(token)
        session = SessionInfo(
            user_id=claims.get("sub", ""),
            email=claims.get("email", "service-token"),
            organization_id=claims.get("organization_id", ""),
            organization_name=claims.get("organization_name", ""),
            workspace_id=workspace_id,
            workspace_name=claims.get("workspace_name", ""),
            product=self.product,
            scopes=scopes,
            access_token=token,
            access_token_expires_at=claims.get("exp", 0) * 1.0,
            is_service_token=True,
        )
        profile = AuthProfile(
            name=profile_name,
            product=self.product,
            client_id=self.client_id,
            base_url=self.base_url,
            scopes=scopes,
            active_organization_id=session.organization_id or None,
            active_workspace_id=session.workspace_id,
            user_id=session.user_id,
            email=session.email,
            organization_name=session.organization_name,
            workspace_name=session.workspace_name,
            is_service_token=True,
        )
        self._profiles.add_profile(profile)
        self._store.set(profile_name, "service_token", token)
        self._store.set(
            profile_name,
            ACCESS_TOKEN_KEY,
            token,
        )
        self._store.set(
            profile_name,
            ACCESS_TOKEN_EXPIRES_AT_KEY,
            str(session.access_token_expires_at),
        )
        self._profiles.set_active_profile(profile_name)
        return LoginResult(profile=profile, session=session, backend_name=self._store.backend_name())

    # ---- Status & logout ---------------------------------------------

    def status(self) -> Optional[SessionInfo]:
        profile = self._profiles.get_active_profile()
        if profile is None:
            return None
        access_token = self._store.get(profile.name, ACCESS_TOKEN_KEY)
        expires_at = self._store.get(profile.name, ACCESS_TOKEN_EXPIRES_AT_KEY)
        expires_at_f = float(expires_at) if expires_at else 0.0
        is_service = bool(profile.is_service_token)
        secret_key = "service_token" if is_service else REFRESH_TOKEN_KEY
        has_stored_secret = self._store.get(profile.name, secret_key) is not None
        return SessionInfo(
            user_id=profile.user_id or "",
            email=profile.email or "",
            organization_id=profile.active_organization_id or "",
            organization_name=profile.organization_name or "",
            workspace_id=profile.active_workspace_id or "",
            workspace_name=profile.workspace_name or "",
            product=profile.product,
            scopes=list(profile.scopes),
            access_token=access_token or "",
            access_token_expires_at=expires_at_f,
            is_service_token=is_service,
        ) if (access_token or has_stored_secret) else None

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing silently if needed.

        Raises ``AuthError`` if no session exists or refresh fails.
        """
        profile = self._profiles.get_active_profile()
        if profile is None:
            raise AuthError("Not logged in. Run `workflo login` to authenticate.")
        if profile.is_service_token:
            token = self._store.get(profile.name, "service_token")
            if token is None:
                raise AuthError("Service token not found. Re-create it from the dashboard.")
            return token

        access_token = self._store.get(profile.name, ACCESS_TOKEN_KEY)
        expires_at = self._store.get(profile.name, ACCESS_TOKEN_EXPIRES_AT_KEY)
        if access_token and expires_at and time.time() < float(expires_at):
            return access_token
        refresh_token = self._store.get(profile.name, REFRESH_TOKEN_KEY)
        if refresh_token is None:
            raise AuthError("Refresh token missing. Run `workflo login` to authenticate.")
        return self._refresh(profile.name, refresh_token)

    def _refresh(self, profile_name: str, refresh_token: str) -> str:
        token = self._client.refresh_token(refresh_token)
        self._store_access_token(profile_name, token)
        if token.refresh_token and token.refresh_token != refresh_token:
            self._store_refresh_token(profile_name, token.refresh_token)
        return token.access_token

    def logout(self) -> None:
        profile = self._profiles.get_active_profile()
        if profile is None:
            return
        if profile.is_service_token:
            self._store.delete(profile.name, "service_token")
        else:
            refresh_token = self._store.get(profile.name, REFRESH_TOKEN_KEY)
            if refresh_token is not None:
                try:
                    self._client.revoke_token(refresh_token, token_type_hint="refresh_token")
                except DeviceAuthError:
                    pass
        self._store.delete(profile.name, ACCESS_TOKEN_KEY)
        self._store.delete(profile.name, ACCESS_TOKEN_EXPIRES_AT_KEY)
        self._store.delete(profile.name, REFRESH_TOKEN_KEY)
        self._profiles.remove_profile(profile.name)

    # ---- Profile helpers ---------------------------------------------

    def list_profiles(self) -> list[AuthProfile]:
        return self._profiles.list_profiles()

    def switch_profile(self, name: str) -> None:
        self._profiles.set_active_profile(name)

    def set_active_org(self, org_id: str, org_name: Optional[str] = None) -> None:
        profile = self._profiles.get_active_profile()
        if profile is None:
            raise AuthError("Not logged in. Run `workflo login` first.")
        self._profiles.set_active_org(profile.name, org_id, org_name)

    def set_active_workspace(self, workspace_id: str, workspace_name: Optional[str] = None) -> None:
        profile = self._profiles.get_active_profile()
        if profile is None:
            raise AuthError("Not logged in. Run `workflo login` first.")
        self._profiles.set_active_workspace(profile.name, workspace_id, workspace_name)

    # ---- Internal token storage --------------------------------------

    def _store_access_token(self, profile_name: str, token: TokenResponse) -> None:
        self._store.set(profile_name, ACCESS_TOKEN_KEY, token.access_token)
        self._store.set(
            profile_name,
            ACCESS_TOKEN_EXPIRES_AT_KEY,
            str(token.expires_at),
        )

    def _store_refresh_token(self, profile_name: str, refresh_token: str) -> None:
        self._store.set(profile_name, REFRESH_TOKEN_KEY, refresh_token)


class AuthError(Exception):
    """Raised when an authenticated action is attempted without a session."""


# ---- Helpers ----------------------------------------------------------


def _decode_jwt_claims(token: str) -> dict:
    """Decode the payload claims of a JWT without verifying the signature.

    Used only for local display (organization name, workspace, email). The
    authorization server signs the token; signature verification happens
    server-side on every API call.
    """
    try:
        import base64

        parts = token.split(".")
        if len(parts) < 2:
            return {}
        # JWT base64url, no padding.
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        import json

        data = json.loads(payload.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _try_open_browser(url: str) -> bool:
    """Attempt to open the default browser. Returns True on success.

    Errors are swallowed — the CLI falls back to printing the URL for the
    user to open manually.
    """
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False
