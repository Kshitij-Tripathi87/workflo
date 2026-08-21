"""JWT-claim-based tenant resolver.

Decodes the bearer token's payload (without verifying the signature — testing
mode only) and injects the `tenant_id` claim into a configurable header. This
is useful for systems where the tenant id travels inside the JWT itself and
the API either trusts that claim or echoes it back via a header.
"""

import base64
import json

from workflo.adapters.protocols import TenantAwareRequest


class JWTTenantResolver:
    name = "jwt"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.claim = cfg.get("claim", "tenant_id")
        self.header_name = cfg.get("header_name", "X-Tenant-ID")

    def configure(self, config: dict) -> None:
        self.claim = config.get("claim", self.claim)
        self.header_name = config.get("header_name", self.header_name)

    def apply(self, request: TenantAwareRequest, tenant_id: str) -> None:
        # Prefer an explicit tenant_id passed by the caller (the scenario knows
        # which tenant it is acting as). Fall back to the claim in the token
        # if present, so callers can omit tenant_id when driving off the JWT.
        if tenant_id:
            request.headers[self.header_name] = tenant_id
            return

        token = (request.headers.get("Authorization") or "").replace("Bearer ", "")
        claim = _decode_claim(token, self.claim) if token else None
        if claim:
            request.headers[self.header_name] = claim


def _decode_claim(token: str, claim: str):
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(decoded)
        return data.get(claim)
    except Exception:
        return None
