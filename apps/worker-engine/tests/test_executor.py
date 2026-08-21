"""Tests for the executor module."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from workflo_worker.executor import _parse_results, execute_run
from workflo_schema import RunSummary


def test_parse_results_valid():
    """_parse_results parses a JSON report dict with summary and duration."""
    data = {
        "summary": {
            "total": 5,
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "deselected": 0,
        },
        "duration": 12.5,
    }
    results_path = Path("/tmp/fake-results.json")

    with patch.object(Path, "exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=json.dumps(data))
    ):
        summary = _parse_results(results_path)

    assert isinstance(summary, RunSummary)
    assert summary.total == 5
    assert summary.passed == 4
    assert summary.failed == 1
    assert summary.skipped == 0
    assert summary.deselected == 0
    assert summary.duration_seconds == 12.5


def test_parse_results_missing_file_returns_empty_runsummary():
    """_parse_results returns an empty RunSummary when the file doesn't exist."""
    results_path = Path("/tmp/does-not-exist.json")

    with patch.object(Path, "exists", return_value=False):
        summary = _parse_results(results_path)

    assert isinstance(summary, RunSummary)
    assert summary.total == 0
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.skipped == 0
    assert summary.deselected == 0
    assert summary.duration_seconds == 0.0


def test_parse_results_partial_summary_uses_defaults():
    """_parse_results handles a summary missing some keys (defaults to 0)."""
    data = {"summary": {"total": 3, "passed": 2}, "duration": 4.2}
    results_path = Path("/tmp/fake-partial.json")

    with patch.object(Path, "exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=json.dumps(data))
    ):
        summary = _parse_results(results_path)

    assert summary.total == 3
    assert summary.passed == 2
    assert summary.failed == 0
    assert summary.skipped == 0
    assert summary.deselected == 0
    assert summary.duration_seconds == 4.2


def test_execute_run_minimal_spec_success():
    """execute_run with a minimal spec returns the parsed RunSummary."""
    spec_dict = {"goal": "smoke"}
    summary_data = {
        "summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0, "deselected": 0},
        "duration": 1.0,
    }
    fake_results_path = "/tmp/fake-run-results.json"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "all good"
    mock_proc.stderr = ""

    streamer = MagicMock()

    with patch(
        "workflo_worker.executor.subprocess.run", return_value=mock_proc
    ) as mock_run, patch(
        "workflo_worker.executor.tempfile.mktemp", return_value=fake_results_path
    ), patch.object(
        Path, "exists", return_value=True
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(summary_data))
    ):
        result = execute_run(spec_dict, streamer)

    assert isinstance(result, RunSummary)
    assert result.total == 2
    assert result.passed == 2
    assert result.failed == 0
    # subprocess.run must have been called once
    mock_run.assert_called_once()
    # Streamer gets at least one log call (the "Executing pytest..." line)
    assert streamer.log.call_count >= 1


def test_execute_run_markers_not_passed_to_pytest():
    """Markers from the spec are NOT passed to pytest via -m.

    The spec's markers are workflo's internal probe-group labels
    (e.g. ["surface"], ["deep", "security"]), NOT pytest markers.
    Passing them as pytest's -m would deselect every test that doesn't
    have an explicit @pytest.mark.surface decorator — which is every
    test in a typical repo. The worker engine treats markers as
    probe-group identification only; pytest runs the repo's whole suite
    unfiltered for surface tests.
    """
    spec_dict = {"goal": "security", "markers": ["security", "regression"]}
    summary_data = {
        "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "deselected": 0},
        "duration": 0.0,
    }
    fake_results_path = "/tmp/fake-run-results-markers.json"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    streamer = MagicMock()

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return mock_proc

    with patch(
        "workflo_worker.executor.subprocess.run", side_effect=fake_run
    ), patch(
        "workflo_worker.executor.tempfile.mktemp", return_value=fake_results_path
    ), patch.object(
        Path, "exists", return_value=True
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(summary_data))
    ):
        execute_run(spec_dict, streamer)

    # The pytest marker flag `-m` should NOT be present (markers are
    # workflo's internal labels, not pytest markers).
    # But python's `-m pytest` flag WILL be present.
    # We need to distinguish: pytest's -m is followed by a marker expression,
    # python's -m is followed by "pytest".
    pytest_m_flags = [i for i, v in enumerate(captured_cmd) if v == "-m"]
    pytest_marker_flags = [
        i for i in pytest_m_flags
        if i + 1 < len(captured_cmd) and captured_cmd[i + 1] != "pytest"
    ]
    assert pytest_marker_flags == [], (
        f"pytest's -m marker flag should not be present; "
        f"got marker flags at indices {pytest_marker_flags} in {captured_cmd}"
    )


def test_execute_run_no_pytest_m_argument():
    """When no markers are present, pytest's -m is omitted (python's -m pytest remains)."""
    spec_dict = {"goal": "smoke", "markers": []}
    summary_data = {
        "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "deselected": 0},
        "duration": 0.0,
    }
    fake_results_path = "/tmp/fake-run-results-no-markers.json"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    streamer = MagicMock()

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return mock_proc

    with patch(
        "workflo_worker.executor.subprocess.run", side_effect=fake_run
    ), patch(
        "workflo_worker.executor.tempfile.mktemp", return_value=fake_results_path
    ), patch.object(
        Path, "exists", return_value=True
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(summary_data))
    ):
        execute_run(spec_dict, streamer)

    # pytest's -m should not be present; python's -m pytest will be
    pytest_m_flags = [i for i, v in enumerate(captured_cmd) if v == "-m"]
    pytest_marker_flags = [
        i for i in pytest_m_flags
        if i + 1 < len(captured_cmd) and captured_cmd[i + 1] != "pytest"
    ]
    assert pytest_marker_flags == []


def test_execute_run_includes_targets_in_cmd():
    """Included test targets are passed to the pytest command."""
    spec_dict = {
        "goal": "smoke",
        "targets": {"include": ["tests/test_a.py", "tests/test_b.py"]},
    }
    summary_data = {
        "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "deselected": 0},
        "duration": 0.0,
    }
    fake_results_path = "/tmp/fake-run-results-targets.json"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    streamer = MagicMock()

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return mock_proc

    with patch(
        "workflo_worker.executor.subprocess.run", side_effect=fake_run
    ), patch(
        "workflo_worker.executor.tempfile.mktemp", return_value=fake_results_path
    ), patch.object(
        Path, "exists", return_value=True
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(summary_data))
    ):
        execute_run(spec_dict, streamer)

    assert "tests/test_a.py" in captured_cmd
    assert "tests/test_b.py" in captured_cmd


def test_execute_run_nonzero_returncode_still_returns_summary():
    """When subprocess returns non-zero, execute_run returns the parsed summary
    (it should not raise) and logs stderr."""
    spec_dict = {"goal": "smoke"}
    summary_data = {
        "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "deselected": 0},
        "duration": 0.5,
    }
    fake_results_path = "/tmp/fake-run-results-fail.json"

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = "stdout content"
    mock_proc.stderr = "stderr content"

    streamer = MagicMock()

    with patch(
        "workflo_worker.executor.subprocess.run", return_value=mock_proc
    ), patch(
        "workflo_worker.executor.tempfile.mktemp", return_value=fake_results_path
    ), patch.object(
        Path, "exists", return_value=True
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(summary_data))
    ):
        result = execute_run(spec_dict, streamer)

    assert isinstance(result, RunSummary)
    assert result.failed == 1
    # streamer.log gets called with stderr when returncode != 0
    log_calls = [c.args[0] for c in streamer.log.call_args_list]
    assert any("stderr" in c.lower() for c in log_calls)
