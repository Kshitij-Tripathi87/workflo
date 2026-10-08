"""Tests for the Cortex Autopilot validation, health, and exception modules."""
import pytest

from app.core.exceptions import (
    ConnectorManifestMissingError,
    ConnectorNotConfiguredError,
    ConnectorConnectionError,
    SnapshotTimeoutError,
    SnapshotEmptyError,
    PolicyViolationError,
    PolicyConfigError,
    DataHubNotFoundError,
)
from app.core.validators import (
    is_valid_urn,
    _validate_urn,
    _normalize_urn,
)


# ---------- Exception hierarchy ----------

def test_connector_manifest_missing_is_file_not_found():
    """ConnectorManifestMissingError must inherit from FileNotFoundError."""
    err = ConnectorManifestMissingError("/tmp/manifest.json")
    assert isinstance(err, FileNotFoundError)
    assert "MANIFEST_MISSING" in err.code
    assert err.hint is not None
    assert "dbt compile" in err.hint


def test_connector_not_configured_lists_missing_fields():
    err = ConnectorNotConfiguredError("snowflake", ["ACCOUNT", "USER"])
    assert "snowflake" in err.message
    assert "ACCOUNT" in err.message
    assert "USER" in err.message
    assert err.details["missing_fields"] == ["ACCOUNT", "USER"]


def test_connector_connection_error_includes_target():
    err = ConnectorConnectionError("dbt", "/var/manifest.json", "permission denied")
    assert "/var/manifest.json" in err.message
    assert "permission denied" in err.message
    assert err.details["target"] == "/var/manifest.json"


def test_snapshot_timeout_error_includes_depth_and_budget():
    err = SnapshotTimeoutError(
        start_urn="urn:dbt:model:shop:orders",
        depth=42,
        budget_seconds=5.0,
    )
    assert "42" in err.message
    assert "5.0" in err.message
    assert "cycle" in err.hint.lower()


def test_snapshot_empty_error_identifies_source():
    err = SnapshotEmptyError("dbt")
    assert "dbt" in err.message
    assert "manifest" in err.hint


def test_policy_violation_error_includes_policy_name():
    err = PolicyViolationError(
        policy_name="BlockCritical",
        verdict="block",
        reason="severity 90 > 75",
        trigger_values={"severity": 90},
    )
    assert "BlockCritical" in err.message
    assert err.details["trigger_values"]["severity"] == 90
    assert err.hint is not None


def test_policy_config_error_includes_raw_payload():
    raw = {"name": "broken", "invalid_field": True}
    err = PolicyConfigError(reason="unknown field", raw=raw)
    assert err.details["raw"] == raw


def test_datahub_not_found_includes_urn():
    err = DataHubNotFoundError("urn:li:dataset:(nonexistent)")
    assert "nonexistent" in err.message


def test_all_errors_have_to_dict():
    """Every CortexError serializes to a JSON-serializable dict."""
    err = PolicyViolationError("BlockCritical", "block", "reason")
    body = err.to_dict()
    assert body["error"] == "POLICY_VIOLATION"
    assert body["message"]
    assert body["details"]["policy_name"] == "BlockCritical"
    assert "hint" in body


# ---------- URN validator ----------

def test_urn_validator_accepts_dbt_model():
    assert _validate_urn("urn:dbt:model:jaffle_shop:orders") == "urn:dbt:model:jaffle_shop:orders"


def test_urn_validator_accepts_snowflake():
    assert _validate_urn("urn:snowflake:table:PROD.PUBLIC.ORDERS") == "urn:snowflake:table:PROD.PUBLIC.ORDERS"


def test_urn_validator_accepts_datahub():
    assert _validate_urn("urn:li:dataset:(urn:li:dataPlatform:hive,orders,PROD)") == "urn:li:dataset:(urn:li:dataPlatform:hive,orders,PROD)"


def test_urn_validator_accepts_permissive_format():
    """Test fixtures and edge cases pass the permissive check."""
    assert _validate_urn("test:isolated") == "test:isolated"


def test_urn_validator_rejects_empty():
    with pytest.raises(ValueError):
        _validate_urn("")


def test_urn_validator_rejects_overlong():
    with pytest.raises(ValueError):
        _validate_urn("urn:dbt:model:" + "x" * 600)


def test_urn_validator_rejects_garbage():
    with pytest.raises(ValueError):
        _validate_urn("!!!not a urn!!!")


def test_urn_normalize_strips_whitespace():
    assert _normalize_urn("  urn:dbt:model:shop:orders  ") == "urn:dbt:model:shop:orders"


def test_is_valid_urn_returns_bool():
    assert is_valid_urn("urn:dbt:model:shop:orders") is True
    assert is_valid_urn("") is False
    assert is_valid_urn(None) is False


# ---------- Health ----------

def test_health_check_returns_structure():
    """get_detailed_health returns a structure with the expected fields."""
    from app.core.health import get_detailed_health
    body = get_detailed_health()
    assert body["name"] == "Cortex Autopilot"
    assert body["version"]
    assert body["status"] in {"ok", "degraded", "down"}
    assert "connectors" in body
    assert "dbt" in body["connectors"]
    assert "snowflake" in body["connectors"]
    assert "datahub" in body["connectors"]
    assert "cache" in body


# ---------- Snapshot cache ----------

def test_snapshot_cache_set_get():
    """Basic round-trip through the TTL cache."""
    from app.core.snapshot_cache import SnapshotCache, get_snapshot_cache

    cache = SnapshotCache(default_ttl_seconds=10.0)
    cache.invalidate()
    cache.set("k1", {"value": 42})
    assert cache.get("k1") == {"value": 42}
    cache.invalidate()
    assert cache.get("k1") is None


def test_snapshot_cache_ttl_expiry(monkeypatch):
    """Expired entries are not returned."""
    import time
    from app.core.snapshot_cache import SnapshotCache

    cache = SnapshotCache(default_ttl_seconds=0.05)
    cache.invalidate()
    cache.set("k", "v")
    assert cache.get("k") == "v"
    time.sleep(0.1)
    assert cache.get("k") is None


def test_snapshot_cache_stats():
    from app.core.snapshot_cache import SnapshotCache

    cache = SnapshotCache(default_ttl_seconds=60.0)
    cache.invalidate()
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    stats = cache.stats()
    assert stats["alive_keys"] == 2
    assert stats["ttl_seconds"] == 60.0


# ---------- Startup checks ----------

def test_startup_checks_pass_with_default_env(monkeypatch):
    """With sensible defaults, startup checks do not raise."""
    from app.core.startup_checks import run_startup_checks

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORTEX_DBT_MANIFEST_PATH", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    # Should not raise.
    assert run_startup_checks() is True


def test_startup_check_fails_on_bad_frontend_url(monkeypatch):
    from app.core.startup_checks import run_startup_checks

    monkeypatch.setenv("FRONTEND_URL", "not-a-url")
    assert run_startup_checks() is False


def test_startup_check_fails_on_missing_dbt_manifest(monkeypatch, tmp_path):
    from app.core.startup_checks import run_startup_checks

    monkeypatch.setenv("CORTEX_DBT_MANIFEST_PATH", str(tmp_path / "does-not-exist.json"))
    assert run_startup_checks() is False
