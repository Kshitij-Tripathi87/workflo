"""OIDC/JWT authentication core.

Validates JWT access tokens issued by an OIDC provider (e.g. Auth0, Okta,
Keycloak). The JWKS (public keys) are cached per issuer.

Roles are read from a custom claim (`https://datahub.cortex/roles`).
Supported roles: admin, analyst, viewer.
"""

import time
from typing import Optional, Literal
from dataclasses import dataclass

from jose import jwt, jwk
from jose.exceptions import JWTError, ExpiredSignatureError
import httpx

from app.core.settings import settings
from app.core.exceptions import CortexAuthError, CortexForbiddenError


Role = Literal["admin", "analyst", "viewer"]

_ROLE_CLAIM = "https://datahub.cortex/roles"
_JWKS_CACHE: dict[str, tuple[list[dict], float]] = {}
_JWKS_TTL_SECONDS = 300  # 5 minutes


@dataclass
class User:
    """Authenticated user."""
    subject: str
    email: Optional[str]
    name: Optional[str]
    roles: list[Role]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def has_role(self, role: Role) -> bool:
        return role in self.roles or self.is_admin


async def _fetch_jwks(issuer: str) -> list[dict]:
    """Fetch and cache JWKS for an issuer."""
    cached = _JWKS_CACHE.get(issuer)
    if cached and time.time() - cached[1] < _JWKS_TTL_SECONDS:
        return cached[0]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{issuer.rstrip('/')}/.well-known/jwks.json")
        resp.raise_for_status()
        keys = resp.json().get("keys", [])

    _JWKS_CACHE[issuer] = (keys, time.time())
    return keys


def _decode_token_unverified(token: str) -> dict:
    """Decode token without verification (for header inspection only)."""
    try:
        return jwt.decode(
            token,
            key="",
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
            },
        )
    except JWTError:
        raise CortexAuthError("Invalid JWT structure")


async def verify_token(token: str) -> User:
    """
    Verify a JWT access token and return the authenticated User.

    Raises CortexAuthError on failure.
    """
    if not settings.OIDC_ISSUER:
        raise CortexAuthError("OIDC not configured on server")

    # Decode header to get kid
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise CortexAuthError("Malformed JWT header")

    kid = unverified_header.get("kid")
    jwks = await _fetch_jwks(settings.OIDC_ISSUER)
    signing_key = None
    for key in jwks:
        if key.get("kid") == kid:
            signing_key = jwk.construct(key)
            break

    if signing_key is None:
        raise CortexAuthError("Unknown signing key (kid mismatch)")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.OIDC_CLIENT_ID,
            issuer=settings.OIDC_ISSUER,
        )
    except ExpiredSignatureError:
        raise CortexAuthError("Token expired")
    except JWTError as e:
        raise CortexAuthError(f"Token verification failed: {e}")

    roles = payload.get(_ROLE_CLAIM, [])
    if isinstance(roles, str):
        roles = [roles]

    return User(
        subject=payload.get("sub", ""),
        email=payload.get("email"),
        name=payload.get("name"),
        roles=roles,
    )


def extract_bearer_token(authorization_header: str | None) -> str:
    """Extract the bearer token from an Authorization header."""
    if not authorization_header:
        raise CortexAuthError("Missing Authorization header")
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise CortexAuthError("Invalid Authorization header format")
    return parts[1]
