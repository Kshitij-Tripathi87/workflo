"""P2 acceptance: production startup is fail-closed.

The guards exist because every checked default is *permissive*: leaving
JWT_SECRET unset signs tokens with a value that ships in this repository,
leaving RLS_ENABLED unset removes the database-side tenant tripwire, and
leaving MASTER_KEK_HEX unset stores credential columns in plaintext. An
operator who forgets one variable gets a silent security downgrade, so the
application must refuse to start instead.

Each test below drives a single variable away from a *fully valid* production
configuration, proving the guard is what fails - not something else in
create_app().
"""

import pytest
from app.core import envelope
from app.core.config import Settings
from app.core.startup_guards import (
    DEFAULT_JWT_SECRET,
    ProductionConfigError,
    enforce_production_config,
    is_production,
    production_config_errors,
)

# A syntactically valid 32-byte AES-256 key (hex), as MASTER_KEK_HEX expects.
VALID_KEK_HEX = "a" * 64
VALID_SECRET = "k" * 48


def _production_settings(**overrides) -> Settings:
    """Settings object in a fully *valid* production posture, then overridden."""
    base: dict = {
        "environment": "production",
        "jwt_secret": VALID_SECRET,
        "rls_enabled": True,
        "master_kek_hex": VALID_KEK_HEX,
        "kek_provider": "static",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_envelope_provider():
    """availability_error() constructs and caches the KEK provider."""
    envelope.reset_provider()
    yield
    envelope.reset_provider()


# --- posture detection ------------------------------------------------------

def test_default_development_settings_are_not_production():
    assert is_production(Settings()) is False
    assert production_config_errors(Settings()) == []


@pytest.mark.parametrize("environment", ["production", "PRODUCTION", "prod", "  Prod  "])
def test_environment_declares_production(environment):
    assert is_production(Settings(environment=environment)) is True


def test_production_flag_declares_production(monkeypatch):
    """PRODUCTION=true must arm the guards on its own."""
    monkeypatch.setenv("PRODUCTION", "true")
    assert is_production(Settings()) is True


def test_production_env_var_reaches_settings(monkeypatch):
    """The env var spelling used in the acceptance criteria actually binds."""
    monkeypatch.setenv("PRODUCTION", "true")
    monkeypatch.setenv("JWT_SECRET", DEFAULT_JWT_SECRET)
    errors = production_config_errors(Settings())
    assert any("JWT_SECRET" in e for e in errors)


# --- the three invariants ---------------------------------------------------

def test_valid_production_configuration_passes():
    assert production_config_errors(_production_settings()) == []


def test_default_jwt_secret_fails_closed():
    errors = production_config_errors(_production_settings(jwt_secret=DEFAULT_JWT_SECRET))
    assert len(errors) == 1
    assert "JWT_SECRET" in errors[0]
    assert DEFAULT_JWT_SECRET in errors[0]


def test_empty_jwt_secret_fails_closed():
    errors = production_config_errors(_production_settings(jwt_secret=""))
    assert any("JWT_SECRET is empty" in e for e in errors)


def test_short_jwt_secret_fails_closed():
    errors = production_config_errors(_production_settings(jwt_secret="tooshort"))
    assert any("shorter than 32 bytes" in e for e in errors)


def test_rls_disabled_fails_closed():
    errors = production_config_errors(_production_settings(rls_enabled=False))
    assert len(errors) == 1
    assert "RLS_ENABLED" in errors[0]


def test_credential_encryption_unavailable_fails_closed():
    errors = production_config_errors(_production_settings(master_kek_hex=""))
    assert len(errors) == 1
    assert "credential encryption is unavailable" in errors[0]
    assert "MASTER_KEK_HEX" in errors[0]


def test_malformed_kek_fails_closed():
    """A key that exists but cannot produce a cipher is still unavailable."""
    errors = production_config_errors(_production_settings(master_kek_hex="not-hex"))
    assert len(errors) == 1
    assert "credential encryption is unavailable" in errors[0]


def test_unsupported_kek_provider_fails_closed():
    """No KMS provider is shipped in this build; claiming one must not be
    silently ignored (the envelope would otherwise fall back to plaintext)."""
    errors = production_config_errors(_production_settings(kek_provider="aws-kms"))
    assert len(errors) == 1
    assert "credential encryption is unavailable" in errors[0]


def test_all_three_problems_are_reported_together():
    """Operators fix the deployment in one pass, not one restart per variable."""
    errors = production_config_errors(
        _production_settings(jwt_secret=DEFAULT_JWT_SECRET, rls_enabled=False, master_kek_hex="")
    )
    assert len(errors) == 3


# --- the guard is fatal, not advisory --------------------------------------

def test_enforce_raises_for_unsafe_production():
    with pytest.raises(ProductionConfigError) as excinfo:
        enforce_production_config(
            _production_settings(jwt_secret=DEFAULT_JWT_SECRET, rls_enabled=False, master_kek_hex="")
        )
    message = str(excinfo.value)
    assert "Refusing to start in production" in message
    # All three problems are actionable from the error alone.
    assert "JWT_SECRET" in message
    assert "RLS_ENABLED" in message
    assert "MASTER_KEK_HEX" in message


def test_app_startup_fails_in_unsafe_production(monkeypatch):
    """create_app() must raise - the process never reaches serving traffic."""
    from app.core.config import settings
    from app.main import create_app

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(settings, "rls_enabled", False)
    monkeypatch.setattr(settings, "master_kek_hex", "")

    with pytest.raises(ProductionConfigError):
        create_app()


def test_app_starts_in_valid_production(monkeypatch):
    from app.core.config import settings
    from app.main import create_app

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", VALID_SECRET)
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "master_kek_hex", VALID_KEK_HEX)
    envelope.reset_provider()

    assert create_app() is not None


def test_guard_does_not_leak_the_secret_value(monkeypatch):
    """Error text is quoted into logs and tickets: it must not echo the key."""
    weak = "s3cret-but-short"
    with pytest.raises(ProductionConfigError) as excinfo:
        enforce_production_config(_production_settings(jwt_secret=weak))
    assert weak not in str(excinfo.value)
