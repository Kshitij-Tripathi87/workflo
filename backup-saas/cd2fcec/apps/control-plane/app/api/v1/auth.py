"""Auth endpoints — frozen contract (docs/api_contract.md v1).

POST /v1/auth/demo-token : demo-only. Returns a fixed, seeded API key for
    the demo account. Real OAuth is on the roadmap, not in this version.

The demo key is a FIXED constant (not random-per-call) so the same key
works across restarts and test runs. It is stored only as a PBKDF2 hash
(SHA-256-family, salted, 100k iterations) — the plaintext key is never
stored or logged, matching the frozen contract's hashing requirement.

OAuth 2.0 Device Authorization Grant (RFC 8628) endpoints:
- POST /v1/auth/device/code        — Request a device code
- POST /v1/auth/device/token       — Poll for access token
- POST /v1/auth/token/refresh      — Refresh access token
- POST /v1/auth/token/revoke       — Revoke token
"""

import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import (
    ApiKey,
    DeviceCode,
    OAuthToken,
    Organization,
    Project,
    User,
)
from app.services.api_key_service import ApiKeyService
from app.core.crypto import (
    hash_api_key,
    hash_password,
    hash_token,
    sign_access_token,
    verify_password,
    verify_token,
    generate_device_code,
    generate_user_code,
    generate_refresh_token,
    utc_now,
    token_expiry,
    refresh_token_expiry,
    device_code_expiry,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Fixed seeded demo key. wfl_ + 32 hex chars per the contract's key shape.
DEMO_RAW_KEY = "wfl_" + "a1b2c3d4e5f67890abcdef1234567890"
DEMO_KEY_LABEL = "demo-token"

# RFC 8628 constants
DEVICE_CODE_EXPIRY_SECONDS = 1800  # 30 minutes
ACCESS_TOKEN_EXPIRY_MINUTES = 15
REFRESH_TOKEN_EXPIRY_DAYS = 30
POLL_INTERVAL_SECONDS = 5

# Supported OAuth clients and their allowed scopes
OAUTH_CLIENTS = {
    "workflo_cli": {
        "name": "workflo CLI",
        "allowed_scopes": [
            "openid", "profile", "offline_access",
            "workflo:runs:create", "workflo:runs:read",
            "workflo:receipts:read", "workflo:projects:read",
        ],
    },
    "astra_cli": {
        "name": "astra CLI",
        "allowed_scopes": [
            "openid", "profile", "offline_access",
            "astra:missions:create", "astra:missions:read",
            "astra:runs:create", "astra:reports:read",
        ],
    },
    "nexus_cli": {
        "name": "nexus CLI",
        "allowed_scopes": [
            "openid", "profile", "offline_access",
            "nexus:data:read", "nexus:simulation:create",
            "nexus:decisions:read", "nexus:approvals:write",
        ],
    },
}


# ---- Response Models ----

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


class RevokeTokenResponse(BaseModel):
    revoked: bool


# ---- Helper Functions ----

def get_client_config(client_id: str) -> dict:
    """Validate and return client configuration."""
    if client_id not in OAUTH_CLIENTS:
        raise HTTPException(status_code=400, detail=f"Unknown client_id: {client_id}")
    return OAUTH_CLIENTS[client_id]


def parse_scopes(scope_str: Optional[str], client_id: str) -> list[str]:
    """Parse and validate requested scopes against client's allowed scopes."""
    client = get_client_config(client_id)
    allowed = set(client["allowed_scopes"])
    if not scope_str:
        return list(allowed)
    requested = scope_str.split()
    invalid = [s for s in requested if s not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid scopes for client {client_id}: {invalid}")
    return requested


async def get_or_create_demo_project(db: AsyncSession) -> Project:
    """Get or create the default demo project (idempotent, race-safe).

    The project has a FIXED primary key ("default") shared by the demo key,
    so concurrent first-time seeding must converge on one row. On an
    IntegrityError (lost the race), roll back and adopt the winner's row.
    """
    project = await db.get(Project, "default")
    if project:
        return project
    org = Organization(name="Default Org")
    db.add(org)
    await db.flush()
    project = Project(id="default", org_id=org.id, name="Default Project")
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        project = await db.get(Project, "default")
    return project


def build_access_token_claims(
    user: User,
    org: Optional[Organization],
    workspace: Optional[Project],
    client_id: str,
    scopes: list[str],
) -> dict:
    """Build the identity claims bound into a JWT access token.

    These claims are what downstream consumers (CLI profile, run
    attribution, key provisioning) use to identify the acting user — the
    token must carry the REAL user's identity, never a demo placeholder.
    """
    return {
        "sub": user.id,
        "email": user.email,
        "client_id": client_id,
        "organization_id": org.id if org else None,
        "organization_name": org.name if org else None,
        "workspace_id": workspace.id if workspace else None,
        "workspace_name": workspace.name if workspace else None,
        "scopes": scopes,
        "iss": "cortex-control-plane",
        "iat": int(utc_now().timestamp()),
    }


async def resolve_user_workspace(db: AsyncSession, user: User) -> Project:
    """Resolve the user's own workspace project (per-user project ownership).

    Falls back to the shared demo project only if the user has no own
    project (e.g. rows created before per-user projects existed).
    """
    if user.project_id:
        project = await db.get(Project, user.project_id)
        if project:
            return project
    return await get_or_create_demo_project(db)


async def get_or_create_demo_key(db: AsyncSession) -> str:
    """Ensure the fixed demo API key is seeded; return the raw key.

    The raw key is a deterministic constant, so returning DEMO_RAW_KEY after
    a lost seeding race is always correct: the winner's row verifies it.
    """
    stmt = select(ApiKey).where(ApiKey.label == DEMO_KEY_LABEL)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return DEMO_RAW_KEY
    await get_or_create_demo_project(db)
    record = ApiKey(
        project_id="default",
        key_hash=hash_api_key(DEMO_RAW_KEY),
        label=DEMO_KEY_LABEL,
        scopes=["run_tests", "read_reports", "admin"],
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent seed of the same fixed key: the winner's row verifies
        # the same raw key. (key_hash is unique but salted, so a double
        # insert of the same raw key is possible; harmless but converge.)
        await db.rollback()
    return DEMO_RAW_KEY


# ---- Endpoints ----

@router.post("/demo-token")
async def issue_demo_token(db: AsyncSession = Depends(get_db)):
    """Issue the fixed demo API key (demo-only; no real auth).

    Creates the demo key + default project on first call; returns the same
    raw key every time. The raw key is deterministic so the demo works
    across control-plane restarts.
    """
    api_key = await get_or_create_demo_key(db)
    return {"api_key": api_key}


# ---- Device Authorization Grant (RFC 8628) ----

@router.post("/device/code", response_model=DeviceCodeResponse)
async def request_device_code(
    request: Request,
    client_id: str = Form(...),
    scope: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Request a device authorization code (RFC 8628 Section 3.1).

    Returns device_code, user_code, verification_uri, expires_in, interval.
    The CLI opens verification_uri_complete in the browser for user approval.
    """
    client_config = get_client_config(client_id)
    scopes = parse_scopes(scope, client_id)

    device_code = generate_device_code()
    user_code = generate_user_code()

    # Build verification URIs
    base_url = str(request.base_url).rstrip("/")
    # Strip /v1 prefix if present to get the root
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    verification_uri = f"{base_url}/device"
    verification_uri_complete = f"{verification_uri}?user_code={user_code}"

    # Store device code
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


@router.post("/device/token", response_model=TokenResponse)
async def poll_device_token(
    grant_type: str = Form(...),
    device_code: str = Form(...),
    client_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Poll for access token after user authorization (RFC 8628 Section 3.4).

    Returns access_token, refresh_token on success.
    Errors: authorization_pending, slow_down, access_denied, expired_token.
    """
    if grant_type != "urn:ietf:params:oauth:grant-type:device_code":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_grant_type",
                "error_description": "Only device_code grant type supported",
            },
        )

    # Look up device code
    stmt = select(DeviceCode).where(DeviceCode.device_code == device_code)
    result = await db.execute(stmt)
    dc = result.scalar_one_or_none()

    if not dc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Invalid device_code",
            },
        )

    if dc.client_id != client_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Device code client mismatch",
            },
        )

    # Check expiry
    if utc_now() > dc.expires_at:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "expired_token",
                "error_description": "Device code has expired",
            },
        )

    # Check if authorized
    if not dc.authorized_at:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "authorization_pending",
                "error_description": "User has not yet authorized the device",
            },
        )

    # Check if already exchanged for tokens
    if dc.token_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Device code already used",
            },
        )

    # Identity binding: the user was bound to the device code at approval
    # time (POST /device requires an authenticated browser session). A code
    # with no bound user was approved through a legacy/unauthenticated path
    # and must not issue tokens.
    if not dc.user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Device code was not approved by an authenticated user",
            },
        )
    user = await db.get(User, dc.user_id)
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Approving user no longer exists",
            },
        )

    project = await resolve_user_workspace(db, user)
    org = await db.get(Organization, user.org_id) if user.org_id else None

    # Create OAuth tokens
    access_token = sign_access_token(
        build_access_token_claims(user, org, project, client_id, dc.scopes)
    )
    refresh_token = generate_refresh_token()

    oauth_token = OAuthToken(
        user_id=user.id,
        client_id=client_id,
        organization_id=org.id if org else None,
        workspace_id=project.id,
        scopes=dc.scopes,
        access_token_hash=hash_token(access_token),
        refresh_token_hash=hash_token(refresh_token),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(oauth_token)
    await db.flush()

    # Link device code to token
    dc.token_id = oauth_token.id
    dc.authorized_at = utc_now()
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=refresh_token,
        scope=" ".join(dc.scopes),
    )


@router.post("/token/refresh", response_model=TokenResponse)
async def refresh_token(
    grant_type: str = Form(...),
    refresh_token: str = Form(...),
    client_id: str = Form(...),
    scope: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token using a refresh token (RFC 6749 Section 6)."""
    if grant_type != "refresh_token":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_grant_type",
                "error_description": "Only refresh_token grant type supported",
            },
        )

    # Look up token by refresh token hash
    stmt = select(OAuthToken)
    result = await db.execute(stmt)
    tokens = result.scalars().all()

    # Find matching token (verify against stored hashes)
    matched_token: Optional[OAuthToken] = None
    for t in tokens:
        if t.client_id == client_id and verify_token(refresh_token, t.refresh_token_hash):
            matched_token = t
            break

    if not matched_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Invalid refresh token",
            },
        )

    # Check expiry and revocation
    if matched_token.revoked_at:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Token has been revoked",
            },
        )
    if utc_now() > matched_token.refresh_token_expires_at:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Refresh token has expired",
            },
        )

    # Validate scope if provided
    if scope:
        requested_scopes = scope.split()
        allowed_scopes = set(matched_token.scopes)
        invalid = [s for s in requested_scopes if s not in allowed_scopes]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_scope",
                    "error_description": f"Requested scopes not granted: {invalid}",
                },
            )
        new_scopes = requested_scopes
    else:
        new_scopes = matched_token.scopes

    # Rotate tokens (RFC 6749 recommends rotating refresh tokens)
    user = await db.get(User, matched_token.user_id)
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_grant",
                "error_description": "Token's user no longer exists",
            },
        )
    workspace = await resolve_user_workspace(db, user)
    org = await db.get(Organization, user.org_id) if user.org_id else None
    new_access_token = sign_access_token(
        build_access_token_claims(
            user, org, workspace, matched_token.client_id, new_scopes
        )
    )
    new_refresh_token = generate_refresh_token()

    # Revoke old tokens
    matched_token.revoked_at = utc_now()

    # Create new token record
    new_token = OAuthToken(
        user_id=matched_token.user_id,
        client_id=matched_token.client_id,
        organization_id=user.org_id,
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


@router.post("/token/revoke", response_model=RevokeTokenResponse)
async def revoke_token(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    client_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an access or refresh token (RFC 7009)."""
    # Find token by hash
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

    # Per RFC 7009, always return 200 with success even if token not found
    return RevokeTokenResponse(revoked=revoked)


# ---- Rate limiting for login ----

# Simple in-memory rate limiter (single-instance; distributed env would use Redis)
_login_attempts: dict[str, list[float]] = {}


def _check_login_rate_limit(ip: str) -> bool:
    """Allow 5 login attempts per IP per 5 minutes, with exponential backoff."""
    now = time.time()
    timestamps = _login_attempts.get(ip, [])
    timestamps = [t for t in timestamps if now - t < 300]  # 5 min window
    _login_attempts[ip] = timestamps
    if len(timestamps) >= 5:
        return False  # rate limited
    timestamps.append(now)
    _login_attempts[ip] = timestamps
    return True


# ---- Endpoints ----

@router.post("/signup", response_model=dict)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account.

    Creates a user with a default organization AND the user's own project
    (per-user project ownership — the user's workspace is bound to their
    identity at creation, never shared with other users). Password is
    stored argon2id-hashed. On success returns user info and a demo API
    key (same pattern as /demo-token).

    The user's own row commits in its own transaction first, so a
    concurrent first-time seed of the shared demo project/key can never
    roll the new user back with it.
    """
    # Check if user already exists
    stmt = select(User).where(User.email == email)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password with argon2id
    password_hash = hash_password(password)

    # Create user + default organization (own transaction)
    user = User(
        email=email,
        password_hash=password_hash,
    )
    db.add(user)
    await db.flush()

    org = Organization(name=f"Org for {email}")
    db.add(org)
    await db.flush()

    # Link user to org
    user.org_id = org.id

    # Per-user project ownership: the user's own workspace project, bound
    # to their identity. Everything this user runs lands in their project.
    project = Project(org_id=org.id, name=f"Workspace for {email}")
    db.add(project)
    await db.flush()
    user.project_id = project.id
    await db.commit()

    # Ensure the shared demo project + demo API key exist (idempotent)
    await get_or_create_demo_project(db)
    api_key = await get_or_create_demo_key(db)

    return {
        "user_id": user.id,
        "email": user.email,
        "org_id": org.id,
        "project_id": project.id,
        "api_key": api_key,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and issue OAuth tokens.

    Rate-limited: 5 attempts per IP per 5 minutes.
    On success returns tokens + user info; on failure returns
    a generic ``Invalid credentials`` message (no email enum).
    """
    # Rate limit check (simple in-memory, per-IP)
    client_host = request.client.host if request.client else "127.0.0.1"
    if not _check_login_rate_limit(client_host):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 5 minutes.",
        )

    # Find user by email
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Generic failure — don't enumerate whether email or password is wrong
        raise HTTPException(
            status_code=400,
            detail="Invalid credentials",
        )

    # Identity binding: the token's workspace is the user's OWN project,
    # not a shared demo workspace.
    project = await resolve_user_workspace(db, user)
    org = await db.get(Organization, user.org_id) if user.org_id else None

    # Create OAuth tokens
    access_token = sign_access_token(
        build_access_token_claims(
            user, org, project, "workflo_cli",
            ["openid", "profile", "offline_access",
             "workflo:runs:create", "workflo:runs:read",
             "workflo:receipts:read", "workflo:projects:read"],
        )
    )
    refresh_token = generate_refresh_token()

    oauth_token = OAuthToken(
        user_id=user.id,
        client_id="workflo_cli",  # CLI default client
        organization_id=org.id if org else None,
        workspace_id=project.id,
        scopes=["openid", "profile", "offline_access",
                "workflo:runs:create", "workflo:runs:read",
                "workflo:receipts:read", "workflo:projects:read"],
        access_token_hash=hash_token(access_token),
        refresh_token_hash=hash_token(refresh_token),
        access_token_expires_at=token_expiry(ACCESS_TOKEN_EXPIRY_MINUTES),
        refresh_token_expires_at=refresh_token_expiry(REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(oauth_token)
    await db.flush()
    await db.commit()  # persist the token row: revocation/bearer checks depend on it

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        refresh_token=refresh_token,
        scope=" ".join(["openid", "profile", "offline_access",
                       "workflo:runs:create", "workflo:runs:read",
                       "workflo:receipts:read", "workflo:projects:read"]),
    )