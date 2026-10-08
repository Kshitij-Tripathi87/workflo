"""Tests for the ResultStreamer."""

from unittest.mock import patch, MagicMock

import httpx

from workflo_worker.streamer import ResultStreamer
from workflo_schema import RunSummary


def _make_streamer(**overrides):
    """Build a ResultStreamer with config values stubbed out for isolation."""
    defaults = {
        "run_id": "run-123",
        "control_plane_url": "http://control.example.test",
        "api_key": "secret-key",
    }
    defaults.update(overrides)
    return ResultStreamer(**defaults)


def test_log_posts_to_correct_url():
    """log() posts to /v1/runs/<run_id>/logs with the log line as a param."""
    streamer = _make_streamer()

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch("workflo_worker.streamer.httpx.Client", return_value=mock_client) as mock_client_cls:
        streamer.log("hello world")

    mock_client_cls.assert_called_once()
    # Verify the headers include the API key
    _, kwargs = mock_client_cls.call_args
    assert kwargs["headers"]["X-TenantShield-Key"] == "secret-key"
    # Verify the post URL and params
    mock_client.post.assert_called_once()
    post_args, post_kwargs = mock_client.post.call_args
    assert post_args[0] == "http://control.example.test/v1/runs/run-123/logs"
    assert post_kwargs["params"] == {"log_line": "hello world"}


def test_log_appends_to_buffer():
    """log() appends the line to the internal log buffer."""
    streamer = _make_streamer()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False

    with patch("workflo_worker.streamer.httpx.Client", return_value=mock_client):
        streamer.log("line one")
        streamer.log("line two")

    assert streamer._log_buffer == ["line one", "line two"]


def test_complete_posts_summary():
    """complete() posts the summary as JSON to /v1/runs/<run_id>/complete."""
    streamer = _make_streamer()
    summary = RunSummary(total=10, passed=8, failed=1, skipped=1, duration_seconds=5.5)

    mock_response = MagicMock()
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch("workflo_worker.streamer.httpx.Client", return_value=mock_client):
        streamer.complete(summary)

    mock_client.post.assert_called_once()
    post_args, post_kwargs = mock_client.post.call_args
    assert post_args[0] == "http://control.example.test/v1/runs/run-123/complete"
    # Body should be the summary dict
    assert post_kwargs["json"]["total"] == 10
    assert post_kwargs["json"]["passed"] == 8
    assert post_kwargs["json"]["failed"] == 1
    assert post_kwargs["json"]["skipped"] == 1


def test_fail_posts_error_info():
    """fail() posts the error info as JSON to /v1/runs/<run_id>/complete."""
    streamer = _make_streamer()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False

    with patch("workflo_worker.streamer.httpx.Client", return_value=mock_client):
        streamer.fail("something blew up")

    mock_client.post.assert_called_once()
    post_args, post_kwargs = mock_client.post.call_args
    assert post_args[0] == "http://control.example.test/v1/runs/run-123/complete"
    assert post_kwargs["json"] == {"status": "failed", "error": "something blew up"}


def test_log_swallows_exceptions():
    """log() swallows exceptions raised by httpx.Client (no raise)."""
    streamer = _make_streamer()

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    with patch("workflo_worker.streamer.httpx.Client", side_effect=boom):
        # Should not raise
        streamer.log("this should not raise")

    # The log line should still be buffered
    assert streamer._log_buffer == ["this should not raise"]


def test_complete_swallows_exceptions():
    """complete() swallows exceptions raised by httpx.Client (no raise)."""
    streamer = _make_streamer()
    summary = RunSummary(total=1, passed=1)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    with patch("workflo_worker.streamer.httpx.Client", side_effect=boom):
        # Should not raise
        streamer.complete(summary)


def test_fail_swallows_exceptions():
    """fail() swallows exceptions raised by httpx.Client (no raise)."""
    streamer = _make_streamer()

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    with patch("workflo_worker.streamer.httpx.Client", side_effect=boom):
        # Should not raise
        streamer.fail("boom")


def test_log_post_exception_inside_post_is_swallowed():
    """If client.post itself raises, log() should still not propagate."""
    streamer = _make_streamer()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = httpx.ConnectError("dropped")

    with patch("workflo_worker.streamer.httpx.Client", return_value=mock_client):
        # Should not raise
        streamer.log("surviving a dropped post")
