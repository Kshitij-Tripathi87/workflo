"""Cortex CLI authentication package.

Implements the OAuth 2.0 Device Authorization Grant (RFC 8628) for the
Cortex CLI family (workflo, astra, nexus). The package provides a shared
auth client, an OS-backed credential store, and profile management so each
product CLI can authenticate through a browser without asking the user to
paste a password or long API token into the terminal.
"""

from cortex_auth.client import DeviceAuthClient, DeviceAuthError, DeviceCodeResponse, TokenResponse
from cortex_auth.credential_store import CredentialStore, get_credential_store
from cortex_auth.profile import (
    AuthProfile,
    ProfileManager,
    SessionInfo,
    ProfileError,
)
from cortex_auth.session import AuthSession, AuthError, LoginResult

__all__ = [
    "DeviceAuthClient",
    "DeviceAuthError",
    "DeviceCodeResponse",
    "TokenResponse",
    "CredentialStore",
    "get_credential_store",
    "AuthProfile",
    "ProfileManager",
    "SessionInfo",
    "ProfileError",
    "AuthSession",
    "AuthError",
    "LoginResult",
]

__version__ = "1.1.0"
