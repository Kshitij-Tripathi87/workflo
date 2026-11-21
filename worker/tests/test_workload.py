"""Fixed safe workload tests: deterministic, offline, honest about failure."""

from __future__ import annotations

import hashlib

from workflo_worker_host.workload import (
    FIXED_WORKLOAD_ID,
    PINNED_MARKER_SHA256,
    run_fixed_workload,
)


def test_pinned_digest_matches_hashlib():
    # The pin must equal sha256(b"workflo-slice-v1") — if either side
    # drifts, the guest determinism check fails loudly instead of silently.
    assert PINNED_MARKER_SHA256 == hashlib.sha256(b"workflo-slice-v1").hexdigest()


def test_workload_passes_in_writable_workspace(tmp_path):
    result = run_fixed_workload(tmp_path)
    assert result["workload_id"] == FIXED_WORKLOAD_ID
    assert result["ok"] is True
    names = {check["name"] for check in result["checks"]}
    assert names == {"workspace_marker", "hash_determinism", "environment_sanity"}
    assert all(check["ok"] for check in result["checks"])
    # The marker file is written where the host can see it.
    assert (tmp_path / "workflo-slice-marker.bin").read_bytes() == b"workflo-slice-v1"


def test_workload_is_deterministic_across_runs(tmp_path):
    first = run_fixed_workload(tmp_path / "a")
    second = run_fixed_workload(tmp_path / "b")
    # completed_at is a timestamp (may differ); everything else must match.
    assert first["workload_id"] == second["workload_id"]
    assert first["ok"] == second["ok"]
    assert [c["name"] for c in first["checks"]] == [
        c["name"] for c in second["checks"]
    ]
    assert [c["ok"] for c in first["checks"]] == [c["ok"] for c in second["checks"]]


def test_workload_reports_failure_when_workspace_unwritable(tmp_path):
    # A file where the directory should be → marker check fails honestly.
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"")
    result = run_fixed_workload(blocker / "nested")
    assert result["ok"] is False
    marker = next(c for c in result["checks"] if c["name"] == "workspace_marker")
    assert marker["ok"] is False
    # Other checks still ran and are reported individually.
    assert len(result["checks"]) == 3
