"""Bearer token auth provider (default).

Returns `Authorization: Bearer <token>`. The token is read from the caller
(bearer token always carries the auth identity; tenant identity is handled
separately by the `TenantResolver`).
"""

from typing import Dict


class BearerAuthProvider:
    name = "bearer"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.header_name = cfg.get("header_name", "Authorization")
        self.token_env_var = cfg.get("token_env_var", "API_AUTH_TOKEN")

    def configure(self, config: dict) -> None:
        self.header_name = config.get("header_name", self.header_name)
        self.token_env_var = config.get("token_env_var", self.token_env_var)

    def auth_headers(self, credentials: str) -> Dict[str, str]:
        if not credentials:
            return {}
        return {self.header_name: f"Bearer {credentials}"}
