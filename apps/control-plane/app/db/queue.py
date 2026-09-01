"""In-memory job queue with optional Redis backend.

Uses a simple asyncio Queue for dev/testing. In production, swap to Redis/Celery.
"""

import asyncio
import json
from typing import Optional
from workflo_utils.logging import get_logger

logger = get_logger(__name__)


class RunQueue:
    """Async job queue for test run specs."""

    def __init__(self):
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._redis = None

    def connect_redis(self, redis_url: str) -> bool:
        """Optionally connect to Redis for distributed queueing."""
        try:
            import redis.asyncio as aioredis
            if redis_url:
                self._redis = aioredis.from_url(redis_url)
                logger.info("queue.redis_connected")
                return True
        except ImportError:
            logger.warning("queue.redis_unavailable_inmemory")
        return False

    async def enqueue(self, run_spec: dict) -> None:
        if self._redis:
            await self._redis.lpush("test-runs", json.dumps(run_spec))
        else:
            await self._queue.put(run_spec)
        logger.info("queue.enqueued", extra={"extra_data": {"run_id": run_spec.get("run_id")}})

    async def dequeue(self, timeout: float = 5.0) -> Optional[dict]:
        if self._redis:
            result = await self._redis.brpop("test-runs", timeout=int(timeout))
            if result:
                _, data = result
                return json.loads(data)
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


# Singleton queue instance
run_queue = RunQueue()
