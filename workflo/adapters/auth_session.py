"""Session-cookie auth provider.

Mirrors the mock server's own auth: a `session_email=<email>` cookie that the
server reads to identify the user (and infer the tenant). Useful for systems
where auth is done via a session cookie rather than a bearer token.
"""

from typing import Dict


class SessionAuthProvider:
    name = "session"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.cookie_name = cfg.get("cookie_name", "session_email")

    def configure(self, config: dict) -> None:
        self.cookie_name = config.get("cookie_name", self.cookie_name)

    def auth_headers(self, credentials: str) -> Dict[str, str]:
        if not credentials:
            return {}
        return {"Cookie": f"{self.cookie_name}={credentials}"}


class APIKeyAuthProvider:
    """API key via a configurable header (e.g. `X-Api-Key`)."""

    name = "api_key"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.header_name = cfg.get("header_name", "X-Api-Key")

    def configure(self, config: dict) -> None:
        self.header_name = config.get("header_name", self.header_name)

    def auth_headers(self, credentials: str) -> Dict[str, str]:
        if not credentials:
            return {}
        return {self.header_name: credentials}
