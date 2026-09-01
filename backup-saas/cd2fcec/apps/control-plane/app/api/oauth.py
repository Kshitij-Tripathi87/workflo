"""Standard RFC 8628 / RFC 6749 OAuth endpoints.

These endpoints use the standard OAuth paths (`/oauth/device/authorize`,
`/oauth/token`, `/oauth/revoke`) expected by the cortex-auth client
library and other OAuth-compatible clients. They are NOT prefixed with
`/v1` because standard OAuth clients expect root-level paths.

The logic delegates to the helpers in `app.api.v1.auth` so there is a
single source of truth for client config, scope validation, and token
generation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import (
    ACCESS_TOKEN_EXPIRY_MINUTES,
    DEVICE_CODE_EXPIRY_SECONDS,
    POLL_INTERVAL_SECONDS,
    REFRESH_TOKEN_EXPIRY_DAYS,
    DeviceCode,
    OAuthToken,
    build_access_token_claims,
    device_code_expiry,
    generate_device_code,
    generate_refresh_token,
    generate_user_code,
    get_client_config,
    hash_token,
    parse_scopes,
    refresh_token_expiry,
    resolve_user_workspace,
    sign_access_token,
    token_expiry,
    utc_now,
    verify_token,
)
from app.core.crypto import utc_now as _utc_now
from app.db.database import get_db
from app.db.models import Organization, User


router = APIRouter(tags=["oauth"])


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str


def _error(error: str, description: str, status: int = 400) -> JSONResponse:
    """Return a standard RFC 8628 error response (not wrapped in `detail`)."""
    return JSONResponse(
        status_code=status,
        content={"error": error, "error_description": description},
    )


@router.post("/oauth/device/authorize", response_model=DeviceCodeResponse)
async def oauth_device_authorize(
    request: Request,
    client_id: str = Form(...),
    scope: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """RFC 8628 Section 3.1 — request a device authorization code."""
    get_client_config(client_id)
    scopes = parse_scopes(scope, client_id)

    device_code = generate_device_code()
    user_code = generate_user_code()

    base_url = str(request.base_url).rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    verification_uri = f"{base_url}/device"
    verification_uri_complete = f"{verification_uri}?user_code={user_code}"

    dc = DeviceCode(
        device_code=device_code,
        user_code=user_code,
        client_id=client_id,
        scopes=scopes,
        expires_at=device_code_expiry(DEVICE_CODE_EXPIRY_SECONDS),
    )
    db.add(dc)
    await db.commit()

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=DEVICE_CODE_EXPIRY_SECONDS,
        interval=POLL_INTERVAL_SECONDS,
    )


@router.post("/oauth/token", response_model=TokenResponse)
async def oauth_token(
    grant_type: str = Form(...),
    device_code: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    client_id: str = Form(...),
    scope: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """RFC 8628 Section 3.4 + RFC 6749 Section 6 — token endpoint.

    Handles two grant types:
    - `urn:ietf:params:oauth:grant-type:device_code` (device flow polling)
    - `refresh_token` (refresh access token)
    """
    get_client_config(client_id)

    if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        return await _handle_device_code_grant(db, device_code, client_id)
    elif grant_type == "refresh_token":
        return await _handle_refresh_grant(db, refresh_token, client_id, scope)
    else:
        return _error("unsupported_grant_type", "Only device_code and refresh_token grant types supported")


async def _handle_device_code_grant(
    db: AsyncSession, device_code: Optional[str], client_id: str
) -> TokenResponse:
    if not device_code:
        return _error("invalid_request", "device_code required")

    stmt = select(DeviceCode).where(DeviceCode.device_code == device_code)
    result = await db.execute(stmt)
    dc = result.scalar_one_or_none()

    if not dc or dc.client_id != client_id:
        return _error("invalid_grant", "Invalid device_code")
    if utc_now() > dc.expires_at:
        return _error("expired_token", "Device code has expired")
    if not dc.authorized_at:
        return _error("authorization_pending", "User has not yet authorized the device")
    if dc.token_id:
        return _error("invalid_grant", "Device code already used")

    # Identity binding: the approving user was bound at POST /device (which
    # requires an authenticated browser session). No bound user => no tokens.
    if not dc.user_id:
        return _error("invalid_grant", "Device code was not approved by an authenticated user")
    user = await db.get(User, dc.user_id)
    if not user:
        return _error("invalid_grant", "Approving user no longer exists")

    project = await resolve_user_workspace(db, user)
    org = await db.get(Organization, user.org_id) if user.org_id else None

    access_token = sign_access_token(
        build_access_token_claims(user, org, project, client_id, dc.scopes)
    )
    refresh_token_str = generate_refresh_token()

    oauth_token = OAuthToken(
        user_id=user.id,
        client_id=client_id,
        organization_id=org.id if org else None,
        workspace_id=project.id,
        scopes=dc.scopes,
        access_token_hash=hash_token(access_token),
        refresh_token_hash=hash_token(refresh_token_str),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(oauth_token)
    await db.flush()

    dc.token_id = oauth_token.id
    dc.authorized_at = utc_now()
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=refresh_token_str,
        scope=" ".join(dc.scopes),
    )


async def _handle_refresh_grant(
    db: AsyncSession,
    refresh_token: Optional[str],
    client_id: str,
    scope: Optional[str],
) -> TokenResponse:
    if not refresh_token:
        return _error("invalid_request", "refresh_token required")

    stmt = select(OAuthToken)
    result = await db.execute(stmt)
    tokens = result.scalars().all()

    matched_token: Optional[OAuthToken] = None
    for t in tokens:
        if t.client_id == client_id and verify_token(refresh_token, t.refresh_token_hash):
            matched_token = t
            break

    if not matched_token:
        return _error("invalid_grant", "Invalid refresh token")
    if matched_token.revoked_at:
        return _error("invalid_grant", "Token has been revoked")
    if utc_now() > matched_token.refresh_token_expires_at:
        return _error("invalid_grant", "Refresh token has expired")

    matched_token_user = await db.get(User, matched_token.user_id)
    if not matched_token_user:
        return _error("invalid_grant", "Token's user no longer exists")
    workspace = await resolve_user_workspace(db, matched_token_user)
    org = await db.get(Organization, matched_token_user.org_id) if matched_token_user.org_id else None

    if scope:
        requested_scopes = scope.split()
        allowed_scopes = set(matched_token.scopes)
        invalid = [s for s in requested_scopes if s not in allowed_scopes]
        if invalid:
            return _error("invalid_scope", f"Requested scopes not granted: {invalid}")
        new_scopes = requested_scopes
    else:
        new_scopes = matched_token.scopes

    new_access_token = sign_access_token(
        build_access_token_claims(
            matched_token_user, org,
            workspace, matched_token.client_id, new_scopes,
        )
    )
    new_refresh_token = generate_refresh_token()

    matched_token.revoked_at = utc_now()

    new_token = OAuthToken(
        user_id=matched_token.user_id,
        client_id=matched_token.client_id,
        organization_id=matched_token_user.org_id,
        workspace_id=workspace.id,
        scopes=new_scopes,
        access_token_hash=hash_token(new_access_token),
        refresh_token_hash=hash_token(new_refresh_token),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(new_token)
    await db.commit()

    return TokenResponse(
        access_token=new_access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=new_refresh_token,
        scope=" ".join(new_scopes),
    )


@router.post("/oauth/revoke")
async def oauth_revoke(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    client_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """RFC 7009 — revoke a token.

    Always returns 200 per RFC 7009, even if the token is not found.
    """
    get_client_config(client_id)

    stmt = select(OAuthToken)
    result = await db.execute(stmt)
    tokens = result.scalars().all()

    revoked = False
    for t in tokens:
        if t.client_id != client_id:
            continue
        if token_type_hint in (None, "refresh_token") and verify_token(token, t.refresh_token_hash):
            t.revoked_at = utc_now()
            revoked = True
        elif token_type_hint in (None, "access_token") and verify_token(token, t.access_token_hash):
            t.revoked_at = utc_now()
            revoked = True

    if revoked:
        await db.commit()

    return {"revoked": revoked}
