"""Day 13 — live run state: writer, reader, and console rendering."""

from __future__ import annotations

import json
import time

from sandbox_runtime.run_state import (
    RunStateWriter,
    STAGE_ORDER,
    find_latest_run,
    load_run_state,
    render_console,
)


def test_writer_creates_and_updates_state(tmp_path):
    writer = RunStateWriter(tmp_path / "run-1")
    assert (tmp_path / "run-1" / "run_state.json").exists()

    writer.on_stage("snapshot", "active")
    writer.on_event("snapshot_created", {"tree_sha256": "ab" * 32})
    writer.on_stage("tests", "active")
    writer.on_event("AGENT_REPORTED", {
        "steps_total": 4, "steps_completed": 3, "steps_failed": 1,
        "tool_calls": 9, "denied_attempts": 1,
    })
    writer.on_event("FINDINGS_JUDGED", {"confirmed": 1, "reported": 2})
    writer.finish("failed", "agent")

    state = load_run_state(tmp_path / "run-1" / "run_state.json")
    assert state["status"] == "failed"
    assert state["failure_stage"] == "agent"
    assert state["stages"]["agent"] == "fail"
    assert state["agent"]["tool_calls"] == 9
    assert state["findings"] == {"confirmed": 1, "reported": 2}
    # The monotonic bookkeeping field must never leak into the file
    assert "started_monotonic" not in json.dumps(
        (tmp_path / "run-1" / "run_state.json").read_text())


def test_state_file_is_atomically_replaced(tmp_path):
    writer = RunStateWriter(tmp_path / "run-2")
    for i in range(30):
        writer.on_event(f"EV_{i}", {"n": i})
    state = load_run_state(tmp_path / "run-2" / "run_state.json")
    # Recent-events cap keeps the file small — the console must stay cheap.
    assert len(state["recent_events"]) <= 25
    assert state["recent_events"][-1]["event"] == "EV_29"


def test_long_details_are_truncated(tmp_path):
    writer = RunStateWriter(tmp_path / "run-3")
    writer.on_event("BIG", {"blob": "x" * 5000})
    state = load_run_state(tmp_path / "run-3" / "run_state.json")
    assert len(state["recent_events"][0]["detail"]["blob"]) <= 160


def test_find_latest_picks_most_recent(tmp_path):
    import os
    older = tmp_path / "a"
    newer = tmp_path / "b"
    RunStateWriter(older)
    time.sleep(0.02)
    RunStateWriter(newer)
    # mtime ordering decides; force a deterministic gap on filesystems
    # with coarse mtime granularity.
    os.utime(newer / "run_state.json", None)
    found = find_latest_run(tmp_path)
    assert found is not None
    assert found.parent.name == "b"


def test_render_marks_stage_statuses():
    writer_state = {
        "sandbox_id": "sb-1",
        "status": "running",
        "stage": "agent",
        "stages": {"preflight": "pass", "snapshot": "pass", "agent": "active"},
        "agent": {"tool_calls": 5, "denied_attempts": 1,
                  "steps_total": 4, "steps_completed": 3},
        "findings": {"confirmed": 1, "reported": 0},
        "recent_events": [{"event": "AGENT_TOOL_CALL"}],
    }
    console = render_console(writer_state)
    assert "✓ PREFLIGHT" in console
    assert "● AGENT" in console
    assert "5 tool calls" in console
    assert "1 confirmed" in console
    for stage in STAGE_ORDER:
        assert stage.upper() in console


def test_load_missing_state_returns_none(tmp_path):
    assert load_run_state(tmp_path / "nope.json") is None
