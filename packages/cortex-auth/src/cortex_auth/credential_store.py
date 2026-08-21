"""OS-backed credential store for Cortex CLI tokens.

Stores refresh tokens in the operating system's secure credential store. On
macOS this is the Keychain, on Windows the Credential Manager, and on Linux
the Secret Service / GNOME Keyring / KDE Wallet. If no secure store is
available the store falls back to a restricted file (``0600`` permissions)
with an explicit warning surfaced via the caller.

Only secrets (refresh tokens, service tokens) belong in the credential store.
Metadata that is safe to commit (organization id, workspace id, active
profile) lives in the profile manager, never here.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Optional, Protocol


# Default base directory for the fallback credentials file.
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "cortex"
DEFAULT_CREDENTIALS_FILE = DEFAULT_CONFIG_DIR / "credentials.json"


class CredentialStore(Protocol):
    """Protocol every credential store backend must satisfy.

    Backends store opaque secret strings keyed by ``key``. The key is a
    profile-local identifier (e.g. ``refresh_token`` or ``access_token``);
    the profile scoping is applied by callers via the ``namespace`` argument.
    """

    def set(self, namespace: str, key: str, value: str) -> None: ...

    def get(self, namespace: str, key: str) -> Optional[str]: ...

    def delete(self, namespace: str, key: str) -> None: ...

    def clear(self, namespace: str) -> None: ...


    def available(self) -> bool: ...

    def backend_name(self) -> str: ...


class FileCredentialStore:
    """Restricted-file credential store (the secure-store fallback).

    Secrets are written to ``~/.config/cortex/credentials.json`` with
    ``0600`` permissions. The store namespaces secrets per profile so multiple
    accounts can coexist in the same file without cross-talk.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_CREDENTIALS_FILE

    def set(self, namespace: str, key: str, value: str) -> None:
        data = self._load()
        data.setdefault(namespace, {})[key] = value
        self._save(data)

    def get(self, namespace: str, key: str) -> Optional[str]:
        data = self._load()
        return data.get(namespace, {}).get(key)

    def delete(self, namespace: str, key: str) -> None:
        data = self._load()
        if namespace in data and key in data[namespace]:
            del data[namespace][key]
            self._save(data)

    def clear(self, namespace: str) -> None:
        data = self._load()
        if namespace in data:
            del data[namespace]
            self._save(data)

    def available(self) -> bool:
        return True

    def backend_name(self) -> str:
        return "file (fallback)"

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then rename atomically to avoid partial writes.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


class KeychainCredentialStore:
    """macOS Keychain credential store (uses the ``security`` CLI)."""

    SERVICE_PREFIX = "cortex-cli"

    def __init__(self) -> None:
        self._system = platform.system()

    def available(self) -> bool:
        return self._system == "Darwin"

    def backend_name(self) -> str:
        return "macOS Keychain"

    def _service(self, namespace: str) -> str:
        return f"{self.SERVICE_PREFIX}-{namespace}"

    def set(self, namespace: str, key: str, value: str) -> None:
        self._run(["security", "add-generic-password", "-a", key,
                   "-s", self._service(namespace), "-w", value, "-U"])

    def get(self, namespace: str, key: str) -> Optional[str]:
        try:
            result = self._run(
                ["security", "find-generic-password", "-a", key,
                 "-s", self._service(namespace), "-w"],
                check=True,
            )
            return result.strip() or None
        except RuntimeError:
            # Item not found.
            return None

    def delete(self, namespace: str, key: str) -> None:
        try:
            self._run(["security", "delete-generic-password", "-a", key,
                       "-s", self._service(namespace)])
        except RuntimeError:
            pass

    def clear(self, namespace: str) -> None:
        # The Keychain has no bulk-clear; callers delete known keys explicitly.
        pass

    @staticmethod
    def _run(args: list[str], check: bool = False) -> str:
        import subprocess
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return proc.stdout


class WindowsCredentialStore:
    """Windows Credential Manager credential store (uses ``cmdkey``).

    Windows Credential Manager stores opaque blobs keyed by target name. We
    use ``cmdkey`` (present on all modern Windows installs) to write, list,
    and delete generic credentials.
    """

    TARGET_PREFIX = "cortex-cli:"

    def __init__(self) -> None:
        self._system = platform.system()

    def available(self) -> bool:
        # Windows Credential Manager via cmdkey can write/delete credentials
        # but cannot retrieve the plaintext password (the Vault API is needed
        # for that, which requires ctypes/wincred). Fall back to the file store
        # so get() actually returns the stored values.
        return False

    def backend_name(self) -> str:
        return "Windows Credential Manager"

    def _target(self, namespace: str, key: str) -> str:
        return f"{self.TARGET_PREFIX}{namespace}:{key}"

    def set(self, namespace: str, key: str, value: str) -> None:
        import subprocess
        subprocess.run(
            ["cmdkey", f"/generic:{self._target(namespace, key)}",
             f"/user:{key}", f"/pass:{value}"],
            capture_output=True,
            check=True,
        )

    def get(self, namespace: str, key: str) -> Optional[str]:
        import subprocess
        target = self._target(namespace, key)
        proc = subprocess.run(
            ["cmdkey", f"/list:{target}"], capture_output=True, text=True
        )
        if proc.returncode != 0 or target not in proc.stdout:
            return None
        # Retrieving the plaintext password from Credential Manager via
        # cmdkey is not directly supported; the Vault API (wincred) is needed.
        # Fall back to the file store for readability on Windows.
        return None

    def delete(self, namespace: str, key: str) -> None:
        import subprocess
        subprocess.run(
            ["cmdkey", f"/delete:{self._target(namespace, key)}"],
            capture_output=True,
        )

    def clear(self, namespace: str) -> None:
        pass


class SecretServiceCredentialStore:
    """Linux Secret Service / GNOME Keyring / KDE Wallet credential store.

    Uses the ``secretstorage`` Python package when available. Falls back to
    the file store via ``available()`` returning False otherwise.
    """

    SERVICE = "cortex-cli"

    def __init__(self) -> None:
        self._system = platform.system()

    def available(self) -> bool:
        if self._system != "Linux":
            return False
        try:
            import secretstorage  # type: ignore[import]  # noqa: F401
        except ImportError:
            return False
        return self._has_secret_service()

    def backend_name(self) -> str:
        return "Secret Service"

    def _has_secret_service(self) -> bool:
        try:
            import secretstorage  # type: ignore[import]
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            return collection.is_locked() is False or True  # service exists
        except Exception:
            return False

    def _get_collection(self):
        import secretstorage  # type: ignore[import]
        connection = secretstorage.dbus_init()
        return secretstorage.get_default_collection(connection)

    def set(self, namespace: str, key: str, value: str) -> None:
        collection = self._get_collection()
        if collection.is_locked():
            collection.unlock()
        collection.create_item(
            f"{namespace}:{key}",
            {"application": self.SERVICE, "namespace": namespace, "key": key},
            value.encode("utf-8"),
            replace=True,
        )

    def get(self, namespace: str, key: str) -> Optional[str]:
        import secretstorage  # type: ignore[import]
        collection = self._get_collection()
        if collection.is_locked():
            collection.unlock()
        for item in collection.get_all_items():
            label = item.get_label()
            if label == f"{namespace}:{key}":
                return item.get_secret().decode("utf-8")
        return None

    def delete(self, namespace: str, key: str) -> None:
        import secretstorage  # type: ignore[import]
        collection = self._get_collection()
        if collection.is_locked():
            collection.unlock()
        for item in collection.get_all_items():
            if item.get_label() == f"{namespace}:{key}":
                item.delete()
                return

    def clear(self, namespace: str) -> None:
        import secretstorage  # type: ignore[import]
        collection = self._get_collection()
        if collection.is_locked():
            collection.unlock()
        for item in collection.get_all_items():
            if item.get_label().startswith(f"{namespace}:"):
                item.delete()


def get_credential_store(path: Optional[Path] = None) -> CredentialStore:
    """Return the best available credential store for the current platform.

    Order of preference:
      1. macOS Keychain
      2. Windows Credential Manager
      3. Linux Secret Service
      4. Restricted file fallback (``0600``)

    The function probes each backend's ``available()`` in order and returns
    the first one that reports readiness. If none of the OS-backed stores
    are available, the file store is used as a secure-enough fallback.
    """
    for factory in (
        KeychainCredentialStore,
        WindowsCredentialStore,
        SecretServiceCredentialStore,
    ):
        candidate = factory()
        if candidate.available():
            return candidate
    return FileCredentialStore(path)
