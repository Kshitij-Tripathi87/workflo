"""Fail-closed production startup guards.

Every setting checked here has a *permissive development default*: a placeholder
JWT secret, RLS off, credential encryption off. Those defaults are correct for
local work - and they are also exactly the configuration an operator ends up
running in production by simply not setting three environment variables. The
security posture then degrades silently: tokens are signed with a value that is
in this file, the database stops enforcing tenant isolation, and credential
columns are written in plaintext.

Rather than trusting operators to remember the variables (and trusting every
future deploy path to pass them), the application refuses to start when
production posture is declared and any of these invariants does not hold.

Production posture is declared by either:
  * ``ENVIRONMENT=production`` (or ``prod``), or
  * ``PRODUCTION=true``

The check runs from :func:`create_app`, i.e. at import time for
``uvicorn app.main:app``, so a misconfigured process dies during startup instead
of serving traffic with a downgraded posture.
"""

from __future__ import annotations

from app.core.config import Settings

# The placeholder shipped in config.py. Its presence in production means the
# operator never set JWT_SECRET, so every token is signed with a public value.
DEFAULT_JWT_SECRET = "change-me-in-production"

# RFC 7518 §3.2: an HMAC key must be at least as long as the hash output it
# signs with (HS256 -> 256 bits / 32 bytes).
MIN_JWT_SECRET_BYTES = 32

PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})


class ProductionConfigError(RuntimeError):
    """Raised instead of starting a production deployment with an unsafe posture."""


def is_production(settings: Settings) -> bool:
    """True when the settings declare a production posture."""
    if bool(getattr(settings, "production", False)):
        return True
    environment = str(getattr(settings, "environment", "") or "").strip().lower()
    return environment in PRODUCTION_ENVIRONMENTS


def production_config_errors(settings: Settings) -> list[str]:
    """Return the list of fatal configuration problems (empty when acceptable).

    Pure function of the settings: no side effects beyond probing the
    credential-encryption provider, which is exactly what a real sealing
    operation would do.
    """
    if not is_production(settings):
        return []

    errors: list[str] = []

    # 1. Token signing key must not be the shipped placeholder or weak.
    secret = str(getattr(settings, "jwt_secret", "") or "").strip()
    if not secret:
        errors.append(
            "JWT_SECRET is empty: access tokens would be signed with an empty key. "
            "Set JWT_SECRET to a random value of at least 32 bytes."
        )
    elif secret == DEFAULT_JWT_SECRET:
        errors.append(
            f"JWT_SECRET is still the shipped placeholder {DEFAULT_JWT_SECRET!r}: "
            "anyone with this source tree could mint valid access tokens. "
            "Set JWT_SECRET to a random value of at least 32 bytes."
        )
    elif len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        errors.append(
            f"JWT_SECRET is shorter than {MIN_JWT_SECRET_BYTES} bytes, which "
            "weakens HS256 signing. Use at least 32 random bytes."
        )

    # 2. Row-level security is the database-side tripwire behind app-layer
    #    tenant scoping; production must not run without it.
    if not bool(getattr(settings, "rls_enabled", False)):
        errors.append(
            "RLS_ENABLED is false: PostgreSQL will not enforce tenant isolation, "
            "leaving application-layer bugs as the only control. Set RLS_ENABLED=true."
        )

    # 3. Credential columns must be encryptable; without a usable KEK the
    #    envelope helpers pass values through in plaintext.
    from app.core import envelope

    kek_reason = envelope.availability_error(settings)
    if kek_reason:
        errors.append(
            f"credential encryption is unavailable ({kek_reason}): credential "
            "columns would be stored in plaintext. Configure MASTER_KEK_HEX "
            "(or a KMS KEK provider) before starting production."
        )

    return errors


def enforce_production_config(settings: Settings) -> None:
    """Raise :class:`ProductionConfigError` if production posture is unsafe.

    Deliberately raises - there is no warning-only mode. A startup that cannot
    satisfy the invariants must not serve requests.
    """
    errors = production_config_errors(settings)
    if not errors:
        return

    details = "\n".join(f"  - {error}" for error in errors)
    raise ProductionConfigError(
        "Refusing to start in production with an unsafe configuration:\n"
        f"{details}\n"
        "Every item above has a permissive development default; production "
        "requires each one to be set explicitly."
    )
