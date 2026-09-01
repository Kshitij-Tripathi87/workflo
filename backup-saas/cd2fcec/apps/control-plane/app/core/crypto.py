"""Cryptographic helpers for API key hashing, token hashing, and verification.

User passwords are hashed with Argon2id (memory-hard, GPU-resistant).
argon2-cffi is a hard dependency — the fallback was removed because
a fast general-purpose hash (SHA-256) is cryptographically wrong for
passwords. If argon2-cffi is not installed, the module will fail fast
with a clear ImportError rather than silently downgrading to an
insecure scheme.
"""

import hashlib
import secrets
import string
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_password_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    """Hash a user password with argon2id (memory-hard, GPU-resistant)."""
    return _password_hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """Verify a raw password against an argon2id hash."""
    try:
        _password_hasher.verify(hashed, raw)
        return True
    except VerifyMismatchError:
        return False


def hash_api_key(raw_key: str) -> str:
    """Hash an API key with a random salt using PBKDF2."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", raw_key.encode(), salt, iterations=100_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against a stored hash."""
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", raw_key.encode(), salt, iterations=100_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def hash_token(raw_token: str) -> str:
    """Hash an OAuth token (access or refresh) with PBKDF2."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", raw_token.encode(), salt, iterations=100_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_token(raw_token: str, stored_hash: str) -> bool:
    """Verify a raw OAuth token against a stored hash."""
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", raw_token.encode(), salt, iterations=100_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def generate_device_code() -> str:
    """Generate a cryptographically secure device code (RFC 8628)."""
    return secrets.token_urlsafe(32)


def generate_user_code() -> str:
    """Generate a user code for device flow (8 chars, alphanumeric)."""
    alphabet = string.ascii_uppercase + string.digits
    # Format as XXXX-XXXX per RFC 8628 common practice
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{part1}-{part2}"


def generate_access_token() -> str:
    """Generate an opaque refresh-style token (legacy path; use JWT for new grants)."""
    return f"wfl_at_{secrets.token_urlsafe(32)}"


def sign_access_token(claims: dict) -> str:
    """Sign an HS256 JWT access token carrying the user's identity claims.

    The CLI decodes these claims (sub, email, organization_*, workspace_*)
    to display the authenticated identity, so the access token MUST be a
    real JWT — an opaque token would silently drop the user's identity
    from every downstream consumer. Standard library only (base64url +
    HMAC-SHA256); no PyJWT dependency.
    """
    import base64
    import hmac
    import json

    from app.core.config import settings

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    payload = dict(claims)
    if "exp" not in payload:
        payload["exp"] = int((utc_now() + timedelta(minutes=settings.jwt_expire_minutes)).timestamp())
    signing_input = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    sig = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def verify_access_token(raw_token: str) -> dict | None:
    """Verify an HS256 JWT access token. Returns claims or None."""
    import base64
    import hmac
    import json

    from app.core.config import settings

    parts = raw_token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        expected = hmac.new(
            settings.jwt_secret.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        supplied = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
        if not isinstance(payload, dict):
            return None
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and exp < utc_now().timestamp():
            return None
        return payload
    except Exception:
        return None


def generate_refresh_token() -> str:
    """Generate a refresh token."""
    return f"wfl_rt_{secrets.token_urlsafe(32)}"


def utc_now() -> datetime:
    # Naive UTC: every comparison in this codebase is naive-vs-naive.
    # (SQLite's DATETIME strips the offset on read-back, so an aware value
    # stored by this helper would be reloaded naive and break comparisons.)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_expiry(minutes: int = 15) -> datetime:
    """Access token expiry (default 15 min per RFC 8628 recommendation)."""
    return utc_now() + timedelta(minutes=minutes)


def refresh_token_expiry(days: int = 30) -> datetime:
    """Refresh token expiry (default 30 days)."""
    return utc_now() + timedelta(days=days)


def device_code_expiry(seconds: int = 1800) -> datetime:
    """Device code expiry (default 30 min per RFC 8628)."""
    return utc_now() + timedelta(seconds=seconds)
