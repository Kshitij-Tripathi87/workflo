"""TTL-based cache for GraphSnapshot objects.

Connectors that read from disk (dbt) or slow external services (DataHub,
Snowflake) benefit from caching. The cache is keyed by the connector
name + an opaque "signature" (typically file mtime + size, or a query
hash) so that changed artifacts invalidate cleanly.

This is intentionally simple — no Redis, no LRU. A single-process dict
with monotonic timestamps is enough for the Impact Gate workflow.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    expires_at: float


class SnapshotCache:
    """Thread-safe TTL cache for GraphSnapshots and connector outputs."""

    def __init__(self, default_ttl_seconds: float = 60.0):
        self._ttl = default_ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        now = time.monotonic()
        with self._lock:
            self._store[key] = CacheEntry(value=value, created_at=now, expires_at=now + ttl)

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            alive = sum(1 for e in self._store.values() if e.expires_at >= now)
            return {
                "total_keys": len(self._store),
                "alive_keys": alive,
                "ttl_seconds": self._ttl,
            }


# Module-level shared cache for connectors
_snapshot_cache = SnapshotCache(default_ttl_seconds=60.0)


def get_snapshot_cache() -> SnapshotCache:
    """Return the process-wide snapshot cache."""
    return _snapshot_cache


def make_cache_key(connector: str, signature: str) -> str:
    """Build a cache key from the connector name and a content signature."""
    return f"{connector}::{signature}"
