"""Native pytest suite for the sample_pkg fixture repo.

These three tests are the surface-tier baseline — they are what `python -m
workflo_worker --spec-file spec.json --repo-path <this repo>` runs
unfiltered with `pytest -v --json-report`. They MUST pass so the surface
run's receipt records `total=3, passed=3` deterministically and downstream
tests can compare against a constant.

The deep/aggressive tier runs the SAME suite PLUS the generated file at
`tests/test_workflo_generated.py` (written by the worker's model stage).
So a deep run reports total=(3 + N) where N is the count of model-proposed
probes. That's the receipt-level difference that proves --deep-test and
--test produce different output.
"""

from __future__ import annotations

from sample_pkg import add, divide, is_host_blocked


def test_add_basic():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_divide_happy_path():
    assert divide(10, 2) == 5.0
    assert divide(7, 1) == 7.0


def test_is_host_blocked_known_evil():
    assert is_host_blocked("evil.example.com") is True
    assert is_host_blocked("good.example.com") is False
