"""Profile and session management for multiple Cortex accounts.

The profile manager stores metadata that is safe to commit (organization id,
workspace id, active profile name) in a TOML-ish config file. Secrets stay in
the credential store, never in the profile file.

Named profiles let a single machine hold several identities (personal and
work, or several organizations). The active profile determines which stored
refresh token is used and which organization/workspace a command targets.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "cortex"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


class ProfileError(Exception):
    """Raised on profile lookup or persistence failures."""


@dataclass
class SessionInfo:
    """The user identity and tokens bound to a profile.

    The ``access_token`` is short-lived (~15 minutes). The ``refresh_token``
    is rotating and stored in the OS credential store; here we keep only the
    non-secret metadata needed to display ``auth status`` and to refresh
    silently. ``refresh_token`` is intentionally NOT persisted to the config
    file — it is held only in memory and written to the credential store.
    """

    user_id: str
    email: str
    organization_id: str
    organization_name: str
    workspace_id: str
    workspace_name: str
    product: str
    scopes: list[str]
    access_token: str = ""
    access_token_expires_at: float = 0.0
    # When True the session was minted from a service token (CI), not a human
    # browser login.
    is_service_token: bool = False

    def is_access_token_valid(self, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        return bool(self.access_token) and current < self.access_token_expires_at

    def to_public_dict(self) -> dict[str, Any]:
        """Return a serializable view without the access token value."""
        data = asdict(self)
        data.pop("access_token", None)
        return data


@dataclass
class AuthProfile:
    """A named login profile (e.g. ``personal``, ``cortex-labs``)."""

    name: str
    product: str
    client_id: str
    base_url: str
    scopes: list[str] = field(default_factory=list)
    active_organization_id: Optional[str] = None
    active_workspace_id: Optional[str] = None
    # Non-secret user metadata, used for ``auth list``.
    user_id: Optional[str] = None
    email: Optional[str] = None
    organization_name: Optional[str] = None
    workspace_name: Optional[str] = None
    is_service_token: bool = False


class ProfileManager:
    """Manages named profiles and the active session for a product CLI.

    The config file stores the list of profile definitions plus which profile
    is currently active. Secrets are never written here — the credential store
    holds refresh tokens keyed by profile name.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_FILE

    # ---- Profile CRUD -------------------------------------------------

    def add_profile(self, profile: AuthProfile) -> None:
        config = self.load()
        profiles = {p["name"]: p for p in config.get("profiles", [])}
        profiles[profile.name] = _profile_to_dict(profile)
        config["profiles"] = list(profiles.values())
        self.save(config)

    def get_profile(self, name: str) -> AuthProfile:
        config = self.load()
        for p in config.get("profiles", []):
            if p.get("name") == name:
                return _profile_from_dict(p)
        raise ProfileError(f"Profile not found: {name}")

    def list_profiles(self) -> list[AuthProfile]:
        config = self.load()
        return [_profile_from_dict(p) for p in config.get("profiles", [])]

    def remove_profile(self, name: str) -> None:
        config = self.load()
        config["profiles"] = [p for p in config.get("profiles", []) if p.get("name") != name]
        if config.get("active_profile") == name:
            config["active_profile"] = None
        self.save(config)

    def update_profile(self, name: str, **changes: Any) -> AuthProfile:
        config = self.load()
        profiles = config.get("profiles", [])
        updated: Optional[AuthProfile] = None
        for p in profiles:
            if p.get("name") == name:
                for key, value in changes.items():
                    p[key] = value
                updated = _profile_from_dict(p)
                break
        if updated is None:
            raise ProfileError(f"Profile not found: {name}")
        self.save(config)
        return updated

    # ---- Active profile ----------------------------------------------

    def get_active_profile_name(self) -> Optional[str]:
        return self.load().get("active_profile")

    def set_active_profile(self, name: str) -> None:
        config = self.load()
        if not any(p.get("name") == name for p in config.get("profiles", [])):
            raise ProfileError(f"Cannot activate unknown profile: {name}")
        config["active_profile"] = name
        self.save(config)

    def get_active_profile(self) -> Optional[AuthProfile]:
        name = self.get_active_profile_name()
        if name is None:
            return None
        try:
            return self.get_profile(name)
        except ProfileError:
            return None

    # ---- Organization/workspace selection -------------------------------

    def set_active_org(self, profile: str, org_id: str, org_name: Optional[str] = None) -> None:
        changes: dict[str, Any] = {"active_organization_id": org_id}
        if org_name is not None:
            changes["organization_name"] = org_name
        self.update_profile(profile, **changes)

    def set_active_workspace(self, profile: str, workspace_id: str, workspace_name: Optional[str] = None) -> None:
        changes: dict[str, Any] = {"active_workspace_id": workspace_id}
        if workspace_name is not None:
            changes["workspace_name"] = workspace_name
        self.update_profile(profile, **changes)

    # ---- Config persistence ------------------------------------------

    def load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileError(f"Cannot read config file {self.config_path}: {exc}") from exc

    def save(self, config: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write.
        tmp = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
        tmp.replace(self.config_path)


def _profile_to_dict(profile: AuthProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "product": profile.product,
        "client_id": profile.client_id,
        "base_url": profile.base_url,
        "scopes": list(profile.scopes),
        "active_organization_id": profile.active_organization_id,
        "active_workspace_id": profile.active_workspace_id,
        "user_id": profile.user_id,
        "email": profile.email,
        "organization_name": profile.organization_name,
        "workspace_name": profile.workspace_name,
        "is_service_token": profile.is_service_token,
    }


def _profile_from_dict(data: dict[str, Any]) -> AuthProfile:
    return AuthProfile(
        name=data["name"],
        product=data.get("product", ""),
        client_id=data.get("client_id", ""),
        base_url=data.get("base_url", ""),
        scopes=list(data.get("scopes", [])),
        active_organization_id=data.get("active_organization_id"),
        active_workspace_id=data.get("active_workspace_id"),
        user_id=data.get("user_id"),
        email=data.get("email"),
        organization_name=data.get("organization_name"),
        workspace_name=data.get("workspace_name"),
        is_service_token=data.get("is_service_token", False),
    )
