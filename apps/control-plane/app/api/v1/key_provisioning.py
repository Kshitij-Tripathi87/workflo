"""Key provisioning endpoints — Cortex directory for receipt provenance.

POST   /v1/auth/keys/provision       Register a public key (requires Bearer auth)
GET    /v1/auth/keys/{key_id}         Fetch public key (public, for verifiers)
POST   /v1/auth/keys/{key_id}/revoke  Revoke a key (requires Bearer auth, same device)

These endpoints implement the provenance guarantee: a receipt signed by
a registered key is traceable to the device + user + org that provisioned
it. The private key never leaves the device.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import utc_now
from app.core.security import verify_bearer_token
from app.db.database import get_db
from app.db.models import ProvisionedKey, User


router = APIRouter(prefix="/auth/keys", tags=["key-provisioning"])


# ---- Request/Response Models ----


class ProvisionRequest(BaseModel):
    public_key: str = Field(..., description="PEM-encoded Ed25519 public key")
    device_id: str = Field(..., description="Unique device identifier")


class ProvisionResponse(BaseModel):
    key_id: str
    fingerprint: str
    device_id: str
    provisioned_at: str


class KeyInfoResponse(BaseModel):
    key_id: str
    public_key: str
    fingerprint: str
    device_id: str
    user_id: str
    organization_id: Optional[str] = None
    provisioned_at: str
    revoked_at: Optional[str] = None
    status: str


class RevokeResponse(BaseModel):
    key_id: str
    revoked: bool
    revoked_at: str


# ---- Helpers ----


def _fingerprint_public_key(pem: str) -> str:
    """Compute SHA-256 fingerprint of a PEM-encoded public key."""
    return hashlib.sha256(pem.encode("utf-8")).hexdigest()


def _iso_z(dt: datetime) -> str:
    """ISO-8601 UTC with a 'Z' suffix, safe for aware or naive inputs."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---- Endpoints ----


@router.post("/provision", response_model=ProvisionResponse)
async def provision_key(
    body: ProvisionRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Register a public key for receipt signing.

    Requires a valid Bearer access token (proves the device completed
    device-flow auth). The private key stays on the device; only the
    public key is registered. Returns the key_id and fingerprint.
    """
    token, user = await verify_bearer_token(authorization, db)

    # Validate the public key format (must be Ed25519 PEM)
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = serialization.load_pem_public_key(body.public_key.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise HTTPException(
                status_code=400,
                detail="Public key must be Ed25519",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid PEM format: {e}")

    fingerprint = _fingerprint_public_key(body.public_key)

    # Check for existing key with same fingerprint (idempotent re-provision)
    stmt = select(ProvisionedKey).where(ProvisionedKey.fingerprint == fingerprint)
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        if existing.status == "revoked":
            raise HTTPException(
                status_code=409,
                detail="This key has been revoked and cannot be re-provisioned",
            )
        if existing.device_id != body.device_id:
            raise HTTPException(
                status_code=409,
                detail="This public key is already provisioned by a different device",
            )
        # Idempotent: return existing key_id
        return ProvisionResponse(
            key_id=existing.id,
            fingerprint=existing.fingerprint,
            device_id=existing.device_id,
            provisioned_at=_iso_z(existing.provisioned_at),
        )

    key_record = ProvisionedKey(
        public_key=body.public_key,
        fingerprint=fingerprint,
        device_id=body.device_id,
        user_id=user.id,
        organization_id=user.org_id,
    )
    db.add(key_record)
    await db.commit()

    return ProvisionResponse(
        key_id=key_record.id,
        fingerprint=key_record.fingerprint,
        device_id=key_record.device_id,
            provisioned_at=_iso_z(key_record.provisioned_at),
    )


@router.get("/{key_id}", response_model=KeyInfoResponse)
async def get_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch public key info by key_id.

    Public endpoint (no auth) — verifiers need this to check signatures
    against registered keys. Returns status so verifiers can reject
    revoked keys.
    """
    stmt = select(ProvisionedKey).where(ProvisionedKey.id == key_id)
    key_record = (await db.execute(stmt)).scalar_one_or_none()

    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found")

    return KeyInfoResponse(
        key_id=key_record.id,
        public_key=key_record.public_key,
        fingerprint=key_record.fingerprint,
        device_id=key_record.device_id,
        user_id=key_record.user_id,
        organization_id=key_record.organization_id,
            provisioned_at=_iso_z(key_record.provisioned_at),
        revoked_at=_iso_z(key_record.revoked_at) if key_record.revoked_at else None,
        status=key_record.status,
    )


@router.post("/{key_id}/revoke", response_model=RevokeResponse)
async def revoke_key(
    key_id: str,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a provisioned key.

    Requires Bearer auth. Only the user who provisioned the key can
    revoke it. Revoked keys remain in the database for audit but are
    marked status=revoked and rejected by verifiers.
    """
    token, user = await verify_bearer_token(authorization, db)

    stmt = select(ProvisionedKey).where(ProvisionedKey.id == key_id)
    key_record = (await db.execute(stmt)).scalar_one_or_none()

    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found")

    # Authorization: same user_id
    if key_record.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only revoke keys you provisioned",
        )

    if key_record.status == "revoked":
        return RevokeResponse(
            key_id=key_record.id,
            revoked=False,
            revoked_at=_iso_z(key_record.revoked_at),
        )

    key_record.status = "revoked"
    key_record.revoked_at = utc_now()
    await db.commit()

    return RevokeResponse(
        key_id=key_record.id,
        revoked=True,
            revoked_at=_iso_z(key_record.revoked_at),
    )
