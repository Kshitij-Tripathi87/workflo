"""Inference scheduler — the component that makes "500 agents" affordable.

The planner/agent ecosystem generates inference demand in BURSTS: N local
agents occasionally need a model decision, then go back to waiting on the
application under test. Running one GPU per agent would bankrupt the
product; this scheduler instead provides BOUNDED, METERED access to a
small model-serving pool:

    agents ──► priority queue ──► batching window ──► model executor
                                     │                    (1..N workers;
                    per-request metrics: queue time,   each holds one
                    inference time, tokens, batch size  in-flight call)

Design notes:

- Thread-based: the existing planner is synchronous (urllib) and is driven
  from the supervisor's executor pool. No asyncio requirement.
- Priority: smaller integer = higher priority (0 is highest). FIFO within
  the same priority.
- Batching: a worker that picks up a request also drains whatever arrived
  during the batch window, up to batch_size, and hands the executor a
  LIST of payloads. The executor contract is one-to-many:
      executor(payloads: list[dict]) -> list[result]
  with results positionally aligned to payloads.
- Cancellation: future.cancel() works until the request is picked up.
- Timeout: enforced on the WAITER side (future.result(timeout=...)) by the
  caller; the scheduler additionally records per-request queue and
  inference time so run metrics can bill acccordingly.
- Metrics: everything the Day-4 benchmark and the pricing model need:
  queue/inferece seconds, batch sizes, counts by outcome, tokens.

Standard library only.
"""

from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from queue import Empty, PriorityQueue
from typing import Any, Callable, Optional


@dataclass(order=True)
class _QueuedRequest:
    priority: int
    seq: int                                # FIFO tie-break within priority
    future: Future = field(compare=False)
    payload: dict = field(compare=False)
    agent_id: str = field(compare=False, default="")
    run_id: str = field(compare=False, default="")
    enqueued_at: float = field(compare=False, default=0.0)


@dataclass
class RequestMetrics:
    request_id: int
    agent_id: str
    run_id: str
    priority: int
    queue_time_s: float = 0.0
    inference_time_s: float = 0.0
    batch_size: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    outcome: str = "pending"   # completed | failed | cancelled
    error: Optional[str] = None


class SchedulerMetrics:
    """Thread-safe aggregate view of everything the run spends on inference."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[RequestMetrics] = []
        self._batches: list[int] = []
        self._started_at = time.monotonic()

    def record(self, rec: RequestMetrics) -> None:
        with self._lock:
            self._records.append(rec)

    def record_batch(self, size: int) -> None:
        with self._lock:
            self._batches.append(size)

    def snapshot(self) -> dict:
        with self._lock:
            records = list(self._records)
            batches = list(self._batches)
            wall = time.monotonic() - self._started_at
        by_outcome: dict[str, int] = {}
        queue_sum = 0.0
        inf_sum = 0.0
        tok_in = tok_out = 0
        for r in records:
            by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
            queue_sum += r.queue_time_s
            inf_sum += r.inference_time_s
            tok_in += r.input_tokens
            tok_out += r.output_tokens
        total = len(records)
        return {
            "wall_time_s": round(wall, 6),
            "requests_total": total,
            "requests_by_outcome": by_outcome,
            "queue_time_s_total": round(queue_sum, 6),
            "inference_time_s_total": round(inf_sum, 6),
            "queue_time_s_mean": round(queue_sum / total, 6) if total else 0.0,
            "inference_time_s_mean": round(inf_sum / total, 6) if total else 0.0,
            "batches": len(batches),
            "batch_size_mean": round(sum(batches) / len(batches), 3) if batches else 0.0,
            "batch_size_max": max(batches) if batches else 0,
            "input_tokens": tok_in,
            "output_tokens": tok_out,
            # Cost-model inputs: GPU-seconds consumed and effective
            # throughput under the observed concurrency.
            "gpu_seconds": round(inf_sum, 6),
            "tokens_per_second": (
                round((tok_in + tok_out) / inf_sum, 2) if inf_sum > 0 else 0.0
            ),
            "requests_per_second": round(total / wall, 3) if wall > 0 else 0.0,
        }


class InferenceScheduler:
    """Bounded, batching, metered access to a model executor.

    executor: callable(list[dict]) -> list[Any]. Each payload dict may
    carry a ``tokens`` key ``{"input": n, "output": n}`` on its RESULT to
    feed the token meters (optional).
    """

    def __init__(
        self,
        executor: Callable[[list[dict]], list[Any]],
        *,
        max_in_flight: int = 4,
        batch_size: int = 8,
        batch_window_s: float = 0.05,
        metrics: Optional[SchedulerMetrics] = None,
    ):
        if max_in_flight < 1:
            raise ValueError("max_in_flight must be >= 1")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._executor = executor
        self.batch_size = batch_size
        self.batch_window_s = batch_window_s
        self._queue: PriorityQueue[_QueuedRequest] = PriorityQueue()
        self._seq = itertools.count(1)
        self._shutdown = threading.Event()
        self.metrics = metrics or SchedulerMetrics()
        self._workers: list[threading.Thread] = []
        for i in range(max_in_flight):
            t = threading.Thread(
                target=self._worker, name=f"workflo-inference-{i}", daemon=True,
            )
            t.start()
            self._workers.append(t)

    # ------------------------------------------------------------------ API

    def submit(self, payload: dict, *, priority: int = 5,
               agent_id: str = "", run_id: str = "") -> Future:
        """Enqueue one inference request. Returns a Future for the result."""
        if self._shutdown.is_set():
            raise RuntimeError("scheduler is shut down")
        future: Future = Future()
        self._queue.put(_QueuedRequest(
            priority=priority, seq=next(self._seq), future=future,
            payload=payload, agent_id=agent_id, run_id=run_id,
            enqueued_at=time.monotonic(),
        ))
        return future

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting work; drain the queue (cancel what's left)."""
        self._shutdown.set()
        while True:
            try:
                req = self._queue.get_nowait()
            except Empty:
                break
            req.future.cancel()
            self.metrics.record(RequestMetrics(
                request_id=req.seq, agent_id=req.agent_id, run_id=req.run_id,
                priority=req.priority, outcome="cancelled",
            ))
        if wait:
            for t in self._workers:
                t.join(timeout=5.0)

    # ------------------------------------------------------------- internals

    def _worker(self) -> None:
        while not (self._shutdown.is_set() and self._queue.empty()):
            try:
                first = self._queue.get(timeout=0.1)
            except Empty:
                continue

            batch = [first]
            # Batching window: also pull whatever else is already waiting,
            # up to batch_size, so one model call serves many agents.
            deadline = time.monotonic() + self.batch_window_s
            while len(batch) < self.batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self._queue.get(timeout=remaining))
                except Empty:
                    break

            self._run_batch(batch)

    def _run_batch(self, batch: list[_QueuedRequest]) -> None:
        live = []
        for req in batch:
            if req.future.set_running_or_notify_cancel():
                live.append(req)
            else:
                # Cancelled while queued.
                self.metrics.record(RequestMetrics(
                    request_id=req.seq, agent_id=req.agent_id,
                    run_id=req.run_id, priority=req.priority,
                    queue_time_s=time.monotonic() - req.enqueued_at,
                    outcome="cancelled",
                ))
        if not live:
            return

        picked_at = time.monotonic()
        for req in live:
            req.future.workflo_queue_time = picked_at - req.enqueued_at  # type: ignore[attr-defined]
        self.metrics.record_batch(len(live))

        try:
            results = self._executor([r.payload for r in live])
            if not isinstance(results, list) or len(results) != len(live):
                raise RuntimeError(
                    "scheduler executor must return one result per payload "
                    f"(got {0 if results is None else len(results)} for {len(live)})"
                )
            finished_at = time.monotonic()
            for req, result in zip(live, results):
                rec = RequestMetrics(
                    request_id=req.seq, agent_id=req.agent_id,
                    run_id=req.run_id, priority=req.priority,
                    queue_time_s=picked_at - req.enqueued_at,
                    inference_time_s=finished_at - picked_at,
                    batch_size=len(live),
                    outcome="completed",
                )
                tokens = getattr(result, "tokens", None) or (
                    result.get("tokens") if isinstance(result, dict) else None
                )
                if isinstance(tokens, dict):
                    rec.input_tokens = int(tokens.get("input", 0) or 0)
                    rec.output_tokens = int(tokens.get("output", 0) or 0)
                self.metrics.record(rec)
                req.future.set_result(result)
        except Exception as e:  # noqa: BLE001 — batch failure fails every member
            finished_at = time.monotonic()
            for req in live:
                self.metrics.record(RequestMetrics(
                    request_id=req.seq, agent_id=req.agent_id,
                    run_id=req.run_id, priority=req.priority,
                    queue_time_s=picked_at - req.enqueued_at,
                    inference_time_s=finished_at - picked_at,
                    batch_size=len(live),
                    outcome="failed", error=str(e)[:200],
                ))
                req.future.set_exception(e)
