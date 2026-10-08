"""Rate limiting — per-tenant and per-IP (SOC 2 CC6.1 / CC7.1).

Two backends behind one interface:

  InMemoryRateLimiter  — single-process default (dev/test). Sliding-window
                         counters keyed by an arbitrary string (tenant
                         ``project_id``, caller IP, ...). A cold restart
                         resets limits — acceptable for single-instance
                         deployments; HA deployments must use Redis.
  RedisRateLimiter     — multi-instance. Fixed window via INCR+EXPIRE,
                         so limits hold across control-plane replicas
                         (INCR is atomic server-side).

For multi-tenancy the important property is the KEY: run submission is
limited per *project* (one tenant cannot starve the shared workers), while
auth attempts are limited per *IP* (credential stuffing defense before a
tenant context exists).
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Protocol

from app.core.config import settings


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record one attempt under ``key``.

        Returns (allowed, retry_after_seconds). ``retry_after_seconds`` is 0
        when allowed; otherwise seconds until the oldest attempt leaves the
        window.
        """


class InMemoryRateLimiter:
    """Sliding-window, process-local limiter."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            timestamps = [t for t in self._buckets.get(key, []) if now - t < window_seconds]
            if len(timestamps) >= limit:
                oldest = timestamps[0]
                retry_after = int(window_seconds - (now - oldest)) + 1
                self._buckets[key] = timestamps
                return False, max(retry_after, 1)
            timestamps.append(now)
            self._buckets[key] = timestamps
            return True, 0

    def clear(self) -> None:
        """Reset all buckets — test isolation hook."""
        with self._lock:
            self._buckets.clear()


class RedisRateLimiter:
    """Fixed-window limiter on shared Redis (multi-instance safe)."""

    def __init__(self, redis_url: str) -> None:
        import redis as redis_lib

        self._client = redis_lib.Redis.from_url(redis_url)

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        rkey = f"rl:{key}"
        # INCR is atomic; the first hit of a window sets its TTL.
        count = int(self._client.incr(rkey))
        if count == 1:
            self._client.expire(rkey, window_seconds)
        if count > limit:
            ttl = int(self._client.ttl(rkey))
            return False, max(ttl, 1)
        return True, 0


_limiter: Optional[RateLimiter] = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    """Process-wide limiter. Redis when configured, in-memory otherwise."""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                if settings.redis_url:
                    _limiter = RedisRateLimiter(settings.redis_url)
                else:
                    _limiter = InMemoryRateLimiter()
    return _limiter


def reset_rate_limits() -> None:
    """Test isolation: forget all current-window state."""
    limiter = get_rate_limiter()
    if isinstance(limiter, InMemoryRateLimiter):
        limiter.clear()


# ---- Endpoint helpers ------------------------------------------------------

# Auth: brute-force defense before any tenant context exists.
LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 300


def check_login_rate_limit(ip: str) -> tuple[bool, int]:
    """5 login attempts per IP per 5 minutes."""
    return get_rate_limiter().hit(f"auth.login:{ip}", LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)


def check_tenant_rate_limit(project_id: str, action: str = "runs.create") -> tuple[bool, int]:
    """Per-tenant run submission ceiling. One noisy project cannot consume
    the whole worker capacity — blast-radius containment for multi-tenancy."""
    return get_rate_limiter().hit(
        f"{action}:{project_id}",
        settings.rate_limit_runs_per_minute,
        60,
    )
