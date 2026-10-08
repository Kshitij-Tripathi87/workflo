"""Inference scheduler tests — batching, priority, cancellation, metrics.

The executor is a local callable here (no model, no network): the scheduler
contract is executor-agnostic, so these tests cover the control flow that
makes 500 logical agents share one model economically.
"""

from __future__ import annotations

import threading
import time

import pytest

from sandbox_runtime.inference_scheduler import (
    InferenceScheduler,
    SchedulerMetrics,
)


def _echo_executor(payloads):
    """1:1 executor: returns each payload's value, tagged with tokens."""
    return [
        {"value": p["value"], "tokens": {"input": 10, "output": 5}}
        for p in payloads
    ]


def test_single_request_round_trip():
    sched = InferenceScheduler(_echo_executor, max_in_flight=1)
    try:
        fut = sched.submit({"value": 41}, agent_id="a1", run_id="r1")
        assert fut.result(timeout=5)["value"] == 41
    finally:
        sched.shutdown()
    snap = sched.metrics.snapshot()
    assert snap["requests_total"] == 1
    assert snap["requests_by_outcome"] == {"completed": 1}
    assert snap["input_tokens"] == 10
    assert snap["output_tokens"] == 5


def test_batching_groups_burst_submissions():
    seen_batches = []

    def recording_executor(payloads):
        seen_batches.append(len(payloads))
        return _echo_executor(payloads)

    sched = InferenceScheduler(
        recording_executor, max_in_flight=1, batch_size=8, batch_window_s=0.2,
    )
    try:
        futs = [sched.submit({"value": i}) for i in range(8)]
        results = [f.result(timeout=5)["value"] for f in futs]
        assert results == list(range(8))
    finally:
        sched.shutdown()
    # One worker pulling within the window should form at least one
    # multi-request batch (exact split is timing-dependent, but the total
    # number of executor calls must be strictly less than 8).
    assert sum(seen_batches) == 8
    assert len(seen_batches) < 8
    snap = sched.metrics.snapshot()
    assert snap["batches"] == len(seen_batches)
    assert snap["batch_size_max"] == max(seen_batches)


def test_priority_ordering():
    order = []
    gate = threading.Event()

    def slow_executor(payloads):
        gate.wait(timeout=5)
        for p in payloads:
            order.append(p["value"])
        return _echo_executor(payloads)

    sched = InferenceScheduler(
        slow_executor, max_in_flight=1, batch_size=1, batch_window_s=0,
    )
    try:
        # Occupy the worker, fill the queue, then release.
        first = sched.submit({"value": "blocker"}, priority=5)
        time.sleep(0.05)  # ensure the blocker is being executed
        low = sched.submit({"value": "low"}, priority=9)
        high = sched.submit({"value": "high"}, priority=1)
        gate.set()
        first.result(timeout=5)
        high.result(timeout=5)
        low.result(timeout=5)
    finally:
        sched.shutdown()
    assert order.index("high") < order.index("low")


def test_cancel_before_pickup():
    gate = threading.Event()

    def blocking_executor(payloads):
        gate.wait(timeout=5)
        return _echo_executor(payloads)

    sched = InferenceScheduler(
        blocking_executor, max_in_flight=1, batch_size=1, batch_window_s=0,
    )
    try:
        blocker = sched.submit({"value": 0})
        time.sleep(0.05)
        fut = sched.submit({"value": 1})
        assert fut.cancel()
        gate.set()
        blocker.result(timeout=5)
        with pytest.raises(Exception):
            fut.result(timeout=5)
    finally:
        sched.shutdown()
    snap = sched.metrics.snapshot()
    assert snap["requests_by_outcome"].get("cancelled") == 1
    assert snap["requests_by_outcome"].get("completed") == 1


def test_executor_failure_fails_exactly_the_batch_members():
    def flaky(payloads):
        raise RuntimeError("model exploded")

    sched = InferenceScheduler(flaky, max_in_flight=2)
    try:
        futs = [sched.submit({"value": i}) for i in range(3)]
        for f in futs:
            with pytest.raises(RuntimeError, match="model exploded"):
                f.result(timeout=5)
    finally:
        sched.shutdown()
    snap = sched.metrics.snapshot()
    assert snap["requests_by_outcome"] == {"failed": 3}


def test_executor_must_return_one_result_per_payload():
    def wrong(payloads):
        return [None] * (len(payloads) + 1)

    sched = InferenceScheduler(wrong, max_in_flight=1)
    try:
        fut = sched.submit({"value": 1})
        with pytest.raises(RuntimeError, match="one result per payload"):
            fut.result(timeout=5)
    finally:
        sched.shutdown()


def test_submit_after_shutdown_rejected():
    sched = InferenceScheduler(_echo_executor)
    sched.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        sched.submit({"value": 1})


def test_metrics_snapshot_shape():
    sched = InferenceScheduler(_echo_executor, max_in_flight=2)
    try:
        futs = [sched.submit({"value": i}, agent_id=f"a{i}", run_id="r")
                for i in range(5)]
        for f in futs:
            f.result(timeout=5)
    finally:
        sched.shutdown()
    snap = sched.metrics.snapshot()
    for key in (
        "wall_time_s", "requests_total", "requests_by_outcome",
        "queue_time_s_total", "inference_time_s_total", "queue_time_s_mean",
        "inference_time_s_mean", "batches", "batch_size_mean",
        "batch_size_max", "input_tokens", "output_tokens",
        "gpu_seconds", "tokens_per_second", "requests_per_second",
    ):
        assert key in snap, key
    assert snap["requests_total"] == 5
    assert snap["input_tokens"] == 50
    assert snap["output_tokens"] == 25
