"""API Key authentication dependency for the Control Plane.

Extracts the API key from the request headers, validates against DB, and
attaches the ApiKey record and its Project to the request state.

Header reconciliation (Phase 3 Track B). Precedence, when several are
present, is the declaration order of `_API_KEY_HEADERS`:
  1. `X-Workflo-Key`  — what the current CLI sends.
  2. `X-API-Key`      — the FROZEN contract header (docs/api_contract.md v1).
  3. `X-TenantShield-Key` — the Phase 1 legacy header, kept until v2.
An earlier version of this docstring claimed `X-API-Key` took precedence;
the code has always returned the first matching header in that order, and the
tuple is now the single definition both `_extract_api_key` and
`optional_api_key` consult so the two cannot drift.

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


_API_KEY_HEADERS = ("X-Workflo-Key", "X-API-Key", "X-TenantShield-Key")


def _extract_api_key(request: Request) -> str:
    """Pull the API key from X-Workflo-Key, X-API-Key, or the legacy header."""
    for header in _API_KEY_HEADERS:
        raw_key = request.headers.get(header)
        if raw_key:
            return raw_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing X-Workflo-Key or X-API-Key header",
    )


async def require_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> ApiKey:
    """FastAPI dependency: extract and validate the API key header."""
    from app.db.database import set_api_key_lookup_mode, set_tenant_context

    raw_key = _extract_api_key(request)
    service = ApiKeyService(db)
    # The hashed key is the only identity known before authentication. Permit
    # the service's key lookup, then it immediately disables this transaction-
    # local mode and switches to the candidate key's project context.
    await set_api_key_lookup_mode(db, enabled=True)
    record = await service.validate_key(raw_key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )
    # RLS tripwire: bind this session's transaction to the key's project
    # so cross-tenant rows are denied by the database too, not just by us.
    await set_tenant_context(db, record.project_id)
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
    subject = claims.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    from app.core import envelope

    # Stored hashes may be envelope-encrypted under the token's org DEK —
    # reveal before the PBKDF2 comparison (legacy plaintext verifies as-is).
    #
    # The candidate set is scoped by the ``sub`` claim of the ALREADY-VERIFIED
    # token, and revoked rows are excluded in SQL. Scanning every token row and
    # running PBKDF2 (100k iterations) against each made one request cost
    # O(all tokens in the system): a caller holding a single valid token could
    # pin the CPU on demand, and the work multiplied across every tenant even
    # though only the caller's own rows can ever match.
    stmt = select(OAuthToken).where(
        OAuthToken.user_id == str(subject),
        OAuthToken.revoked_at.is_(None),
    )
    records = (await db.execute(stmt)).scalars().all()
    record = None
    for t in records:
        stored_access = await envelope.reveal(db, t.organization_id, t.access_token_hash)
        if verify_token(raw_token, stored_access):
            record = t
            break
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


async def optional_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[ApiKey]:
    """Return the caller's API key, or ``None`` when no credential was supplied.

    This distinguishes "anonymous" from "bad credential": a credential that
    IS supplied but invalid still raises 401. Without that distinction an
    attacker could downgrade an authenticated request to the anonymous code
    path simply by sending a junk header.
    """
    if not any(request.headers.get(h) for h in _API_KEY_HEADERS):
        return None
    return await require_api_key(request, db)


def require_scope(scope: str):
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
