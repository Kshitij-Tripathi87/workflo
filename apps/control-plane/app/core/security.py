"""API Key authentication dependency for the Control Plane.

Extracts the API key from the request headers, validates against DB, and
attaches the ApiKey record and its Project to the request state.

Header reconciliation (Phase 3 Track B):
  - `X-API-Key` is the FROZEN contract header (docs/api_contract.md v1).
  - `X-TenantShield-Key` is the legacy header from the Phase 1 control
    plane. It's accepted for backwards compatibility and will be dropped
    in v2. The contract header is checked first; when both are present,
    `X-API-Key` wins.

Bearer access-token verification (identity binding):
  Access tokens are HS256 JWTs signed with the identity claims (sub, email,
  organization_*, workspace_*). Verification checks the signature + expiry,
  then confirms the matching OAuthToken row is not revoked/expired and
  loads the bound User — a valid signature alone is not enough, revocation
  must be honored.
"""

import hashlib
import secrets
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.api_key_service import ApiKeyService
from app.db.models import ApiKey, OAuthToken, User
from app.core.crypto import verify_token, verify_access_token


def _extract_api_key(request: Request) -> str:
    """Pull the API key from the contract header, then the legacy one."""
    raw_key = request.headers.get("X-API-Key")
    if raw_key:
        return raw_key
    raw_key = request.headers.get("X-TenantShield-Key")
    if raw_key:
        return raw_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing X-API-Key header",
    )


async def require_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> ApiKey:
    """FastAPI dependency: extract and validate the API key header."""
    raw_key = _extract_api_key(request)
    service = ApiKeyService(db)
    record = await service.validate_key(raw_key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )
    request.state.api_key = record
    return record


def _extract_bearer_token(authorization: Optional[str]) -> str:
    """Pull the raw token from an Authorization: Bearer header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    raw = authorization[len("Bearer "):].strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token")
    return raw


async def verify_bearer_token(
    authorization: Optional[str],
    db: AsyncSession,
) -> tuple[OAuthToken, User]:
    """Verify a Bearer JWT access token; return (token_record, user).

    The signature and expiry are checked via ``verify_access_token``, then
    the token's OAuthToken row is located by its stored hash to honor
    revocation. The bound user is loaded and returned so callers bind
    identity (user_id / workspace) without an extra round trip.
    """
    raw_token = _extract_bearer_token(authorization)
    claims = verify_access_token(raw_token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    stmt = select(OAuthToken)
    records = (await db.execute(stmt)).scalars().all()
    record = next(
        (t for t in records if not t.revoked_at and verify_token(raw_token, t.access_token_hash)),
        None,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    user = await db.get(User, record.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )
    return record, user


async def require_scope(scope: str):
    """FastAPI dependency factory: enforce a specific API key scope."""
    async def _check(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
        scopes = api_key.scopes if isinstance(api_key.scopes, list) else [api_key.scopes]
        if scope not in scopes and "admin" not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scope: {scope}",
            )
        return api_key
    return _check
