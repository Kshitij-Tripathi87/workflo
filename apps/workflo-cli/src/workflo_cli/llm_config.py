"""LLM configuration storage and validation for the workflo CLI.

Config lives at ~/.config/workflo/config.json under the "llm" key:

    {"llm": {"base_url": "...", "model": "qwen3-4b-4bit", "timeout_seconds": 60}}

The API key is NEVER written to the config file. It goes to the OS
credential store when available (via cortex-auth's CredentialStore), with
a permission-restricted (0600) fallback file alongside the config. On
display surfaces (workflo config list, dry-run plan output) the key is
always redacted — even while the deploy is a placeholder, the redaction
habit is locked in before a real key can ever touch the field.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "workflo"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_KEY_FILE = DEFAULT_CONFIG_DIR / "llm.key"  # credential-store fallback

DEFAULT_MODEL = "qwen3-4b-4bit"
DEFAULT_TIMEOUT_SECONDS = 60

# Marker prefixes that indicate the value is a placeholder, not a real
# endpoint/key. A placeholder present is treated as NOT configured.
_PLACEHOLDER_MARKERS = ("<", "placeholder", "example.com", "your-", "changeme")


class LLMConfigError(Exception):
    """Raised when LLM config is missing or invalid."""


@dataclass
class LLMConfig:
    """Resolved LLM endpoint settings for a deep-tier run."""

    base_url: str
    model: str
    timeout_seconds: int
    api_key: Optional[str]  # None when the key-store lookup missed

    def is_placeholder(self) -> bool:
        """True when the config still holds placeholder-looking values."""
        b = (self.base_url or "").strip().lower()
        if not b:
            return True
        return any(m in b for m in _PLACEHOLDER_MARKERS)


def _config_path() -> Path:
    override = os.environ.get("WORKFLO_CONFIG_DIR")
    if override:
        return Path(override) / "config.json"
    return DEFAULT_CONFIG_FILE


def _key_path() -> Path:
    override = os.environ.get("WORKFLO_CONFIG_DIR")
    if override:
        return Path(override) / "llm.key"
    return DEFAULT_KEY_FILE


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _store_key(api_key: str) -> str:
    """Persist the API key in the OS credential store, falling back to a
    0600 file. Returns a note about which backend held the key."""
    try:
        from cortex_auth.credential_store import get_credential_store

        store = get_credential_store()
        store.set("workflo-llm", "api_key", api_key)
        return store.backend_name()
    except Exception:
        key_file = _key_path()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(api_key, encoding="utf-8")
        try:
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)  # 0600 best effort
        except OSError:
            pass
        return "file-0600 (no OS credential store available)"


def _load_key() -> Optional[str]:
    try:
        from cortex_auth.credential_store import get_credential_store

        store = get_credential_store()
        key = store.get("workflo-llm", "api_key")
        if key:
            return key
    except Exception:
        pass
    key_file = _key_path()
    try:
        if key_file.exists():
            value = key_file.read_text(encoding="utf-8").strip()
            return value or None
    except OSError:
        return None
    return None


def set_llm_config(
    base_url: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Persist LLM settings. Returns a note describing where the key landed."""
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        raise LLMConfigError("base_url must not be empty")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise LLMConfigError("base_url must start with http:// or https://")
    api_key = (api_key or "").strip()
    if not api_key:
        raise LLMConfigError("api_key must not be empty")
    if timeout_seconds < 5 or timeout_seconds > 600:
        raise LLMConfigError("timeout_seconds must be 5..600")

    data = _read_json(_config_path())
    data["llm"] = {
        "base_url": base_url,
        "model": model or DEFAULT_MODEL,
        "timeout_seconds": int(timeout_seconds),
    }
    _write_json(_config_path(), data)
    return _store_key(api_key)


def load_llm_config(include_key: bool = True) -> Optional[LLMConfig]:
    """Load the stored LLM config, or None when never configured."""
    data = _read_json(_config_path()).get("llm")
    if not isinstance(data, dict):
        return None
    return LLMConfig(
        base_url=data.get("base_url", "") or "",
        model=data.get("model", "") or DEFAULT_MODEL,
        timeout_seconds=int(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        api_key=_load_key() if include_key else None,
    )


def clear_llm_config() -> None:
    data = _read_json(_config_path())
    data.pop("llm", None)
    _write_json(_config_path(), data)
    key_file = _key_path()
    if key_file.exists():
        key_file.unlink()


def redact_key(api_key: Optional[str]) -> str:
    """Display form for secrets: never more than the first 4 chars."""
    if not api_key:
        return "(not set)"
    if len(api_key) <= 4:
        return "****"
    return api_key[:4] + "…" + "*" * 8


def describe_llm_config() -> dict:
    """Redacted view for `config list` and the dry-run plan."""
    cfg = load_llm_config(include_key=True)
    if cfg is None:
        return {"configured": False}
    return {
        "configured": True,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "timeout_seconds": cfg.timeout_seconds,
        "api_key": redact_key(cfg.api_key),
        "is_placeholder": cfg.is_placeholder(),
    }


def validate_llm_key(cfg: Optional[LLMConfig] = None, timeout: float = 10.0) -> tuple[bool, str]:
    """Health-check the configured endpoint with the stored key.

    Hits {base_url}/models (OpenAI-compatible listing) and
    {base_url}/health as a fallback — either returning a 2xx/401-vs-200
    distinction counts as an answer. A placeholder config short-circuits
    with an instructive error instead of making any network call.
    """
    import httpx

    cfg = cfg or load_llm_config()
    if cfg is None:
        return False, "LLM not configured — run: workflo config set-llm --base-url <url> --api-key <key>"
    if cfg.is_placeholder():
        return False, (
            f"LLM endpoint looks like a placeholder ({cfg.base_url!r}). "
            "Set a real endpoint: workflo config set-llm --base-url <url> --api-key <key>"
        )
    if not cfg.api_key:
        return False, "LLM api_key missing from credential store — re-run: workflo config set-llm"

    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    # Probe the common health/listing paths used by OpenAI-compatible and
    # vLLM-style servers. Order matters: the first 2xx wins.
    for path in ("/models", "/v1/models", "/health", "/v1/health"):
        url = cfg.base_url + path
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers)
        except httpx.TimeoutException:
            return False, f"timeout contacting {url} (>{timeout}s)"
        except httpx.RequestError as e:
            return False, f"cannot reach {url}: {e}"
        if resp.status_code == 200:
            return True, f"ok ({url} 200)"
        if resp.status_code in (401, 403):
            return False, f"API key rejected by {url} (HTTP {resp.status_code})"
    return False, f"endpoint responded but no health/models endpoint (check base_url)"


def llm_env_for_run(cfg: Optional[LLMConfig] = None) -> dict[str, str]:
    """Env vars the executor injects into the sandbox for the worker."""
    cfg = cfg or load_llm_config()
    if cfg is None or cfg.is_placeholder() or not cfg.api_key:
        return {}
    return {
        "WORKFLO_LLM_BASE_URL": cfg.base_url,
        "WORKFLO_LLM_API_KEY": cfg.api_key,
        "WORKFLO_LLM_MODEL": cfg.model,
        "WORKFLO_LLM_TIMEOUT": str(cfg.timeout_seconds),
    }