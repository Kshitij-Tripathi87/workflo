"""Envelope encryption for credential columns (SOC 2 CC6.7 / CC6.8).

Architecture:

    plaintext credential hash
        └─AES-256-GCM─► field ciphertext        (DEK per organization)
                            wfenc1:v{n}:{nonce}:{ct}

    DEK ──AES-256-GCM──► org_data_keys.wrapped_dek   (KEK, deployment-held)

Why encrypt *hashes*: the columns we protect (API key hashes, OAuth token
hashes, password hashes) are already one-way — the residual risk this kills
is OFFLINE brute force against a stolen database dump. Without the KEK the
hashes stay sealed; with tenant-scoped DEKs, one org's DEK compromise does
not expose another tenant's credentials (blast-radius containment).

KEK providers:
  - ``StaticKEKProvider`` — master_kek_hex from config (dev/test). A loud
    startup pattern; production swaps in a KMS by implementing
    ``KEKProvider`` (wrap/unwrap) — no code changes below that seam.
  - When NO KEK is configured the helpers pass plaintext through, matching
    the codebase's zero-config dev posture (same pattern as jwt_secret).
    is_enabled() is the audit-visible flag; the control plane's /health
    and release checks can assert it is True in production.

Field format: ``wfenc1:v{key_version}:{b64 nonce}:{b64 ciphertext}``.
The prefix is what makes rotation and legacy rows distinguishable at read
time: anything WITHOUT the prefix is a legacy plaintext hash and verifies
through the original hash-verifier path.
"""

from __future__ import annotations

import base64
import secrets
from typing import Optional, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import OrgDataKey

_FIELD_PREFIX = "wfenc1"
_NONCE_LEN = 12  # AES-GCM standard


class EnvelopeError(Exception):
    """Envelope operation failed (misconfiguration or corrupt ciphertext)."""


class KEKProvider(Protocol):
    def wrap(self, dek: bytes) -> str: ...
    def unwrap(self, wrapped: str) -> bytes: ...


class StaticKEKProvider:
    """Dev/test KEK: a 32-byte key from config (master_kek_hex)."""

    def __init__(self, kek_hex: str) -> None:
        try:
            key = bytes.fromhex(kek_hex)
        except ValueError as e:
            raise EnvelopeError("master_kek_hex is not valid hex") from e
        if len(key) != 32:
            raise EnvelopeError("master_kek_hex must decode to 32 bytes (AES-256)")
        self._key = key

    def wrap(self, dek: bytes) -> str:
        nonce = secrets.token_bytes(_NONCE_LEN)
        ct = AESGCM(self._key).encrypt(nonce, dek, None)
        return f"{base64.b64encode(nonce).decode()}:{base64.b64encode(ct).decode()}"

    def unwrap(self, wrapped: str) -> bytes:
        try:
            nonce_b64, ct_b64 = wrapped.split(":")
            return AESGCM(self._key).decrypt(
                base64.b64decode(nonce_b64), base64.b64decode(ct_b64), None
            )
        except Exception as e:
            raise EnvelopeError("failed to unwrap DEK (wrong KEK or corrupt data)") from e


_provider: Optional[KEKProvider] = None


def reset_provider() -> None:
    """Test hook: forget the cached provider so settings changes apply."""
    global _provider
    _provider = None


def is_enabled() -> bool:
    """True when a KEK is configured. Auditors assert True in production."""
    return bool(settings.master_kek_hex)


def availability_error(cfg=None) -> str | None:
    """None when credential encryption is usable, else the reason it is not.

    Used by the fail-closed production startup guard: sealing credential
    columns must not silently degrade to plaintext. The probe validates the key
    material itself, so a malformed MASTER_KEK_HEX fails at startup rather than
    on the first write, and it does not touch the cached provider (callers may
    pass a settings object that is not the process-wide one).
    """
    cfg = cfg if cfg is not None else settings
    if not cfg.master_kek_hex:
        return "no KEK configured (set MASTER_KEK_HEX)"
    if cfg.kek_provider != "static":
        return (
            f"kek_provider {cfg.kek_provider!r} not available in this build "
            "(production deployments install a KMS provider implementing KEKProvider)"
        )
    try:
        StaticKEKProvider(cfg.master_kek_hex)
    except EnvelopeError as e:
        return str(e)
    return None


def _get_provider() -> KEKProvider:
    global _provider
    if _provider is None:
        if not is_enabled():
            raise EnvelopeError("no KEK configured (master_kek_hex empty)")
        if settings.kek_provider != "static":
            raise EnvelopeError(
                f"kek_provider {settings.kek_provider!r} not available in this build "
                "(production deployments install a KMS provider implementing KEKProvider)"
            )
        _provider = StaticKEKProvider(settings.master_kek_hex)
    return _provider


# ---- Field-level helpers ---------------------------------------------------

def is_encrypted(stored: str) -> bool:
    return stored.startswith(_FIELD_PREFIX + ":")


async def _get_or_create_dek(db: AsyncSession, org_id: str) -> OrgDataKey:
    stmt = (
        select(OrgDataKey)
        .where(OrgDataKey.org_id == org_id, OrgDataKey.status == "active")
        .order_by(OrgDataKey.key_version.desc())
    )
    record = (await db.execute(stmt)).scalars().first()
    if record:
        return record
    dek = secrets.token_bytes(32)
    version = 1
    latest = (
        await db.execute(
            select(OrgDataKey)
            .where(OrgDataKey.org_id == org_id)
            .order_by(OrgDataKey.key_version.desc())
        )
    ).scalars().first()
    if latest:
        version = latest.key_version + 1
    record = OrgDataKey(
        org_id=org_id,
        key_version=version,
        wrapped_dek=_get_provider().wrap(dek),
        status="active",
    )
    db.add(record)
    await db.flush()
    return record


async def _dek_for_version(db: AsyncSession, org_id: str, version: int) -> OrgDataKey:
    stmt = select(OrgDataKey).where(
        OrgDataKey.org_id == org_id, OrgDataKey.key_version == version
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise EnvelopeError(f"no DEK for org {org_id} version {version}")
    return record


async def protect(db: AsyncSession, org_id: Optional[str], plaintext: str) -> str:
    """Encrypt a credential column value under the org's active DEK.

    Pass-through when encryption is not configured (zero-config dev) or
    when no org context exists (legacy/demo rows — documented gap).
    """
    if not org_id or not is_enabled():
        return plaintext
    record = await _get_or_create_dek(db, org_id)
    dek = _get_provider().unwrap(record.wrapped_dek)
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), None)
    return (
        f"{_FIELD_PREFIX}:v{record.key_version}:"
        f"{base64.b64encode(nonce).decode()}:{base64.b64encode(ct).decode()}"
    )


async def protect_for_project(db: AsyncSession, project_id: Optional[str], plaintext: str) -> str:
    """Resolve project → org and protect. Rows whose project has no org
    (pre-org legacy data) pass through plaintext — documented gap."""
    if not project_id:
        return await protect(db, None, plaintext)
    from app.db.models import Project

    project = await db.get(Project, project_id)
    org_id = project.org_id if project else None
    return await protect(db, org_id, plaintext)


async def reveal_for_project(db: AsyncSession, project_id: Optional[str], stored: str) -> str:
    if not project_id:
        return await reveal(db, None, stored)
    from app.db.models import Project

    project = await db.get(Project, project_id)
    org_id = project.org_id if project else None
    return await reveal(db, org_id, stored)


async def reveal(db: AsyncSession, org_id: Optional[str], stored: str) -> str:
    """Decrypt a protected value; legacy plaintext passes through so
    pre-encryption rows keep working (verify-then-migrate)."""
    if not is_encrypted(stored):
        return stored
    try:
        _prefix, version_tag, nonce_b64, ct_b64 = stored.split(":")
        version = int(version_tag[1:])
    except (ValueError, IndexError) as e:
        raise EnvelopeError("malformed envelope ciphertext") from e
    if not org_id:
        raise EnvelopeError("encrypted value has no org context for key lookup")
    record = await _dek_for_version(db, org_id, version)
    dek = _get_provider().unwrap(record.wrapped_dek)
    try:
        pt = AESGCM(dek).decrypt(base64.b64decode(nonce_b64), base64.b64decode(ct_b64), None)
    except Exception as e:
        raise EnvelopeError("envelope decryption failed (wrong key or tampered row)") from e
    return pt.decode("utf-8")
