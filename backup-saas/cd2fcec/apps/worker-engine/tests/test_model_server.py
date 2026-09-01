"""Unit tests for workflo_worker.model.model_server.ModelServer.

These back the Phase 1 exit gate for the model stage. They DO NOT require
Ollama to be installed, network access, or a real subprocess — every
external seam (subprocess.Popen, socket.create_connection, requests.post)
is patched. We assert the lifecycle CONTRACT, not integration:

    - start() blocks until the API is reachable, then flips _started=True
    - start() called twice raises (idempotent)
    - start() raises ModelServerError when ollama binary is missing
      (FileNotFoundError from Popen)
    - start() raises ModelServerError when the port is already in use
      AND reuse_existing is False
    - start() with reuse_existing=True adopts an already-running server
      (no Popen, returns immediately)
    - start() kills the spawned subprocess if readiness polling times out
    - generate() before start() raises ModelServerError
    - generate() sends a JSON POST to /api/generate and returns the
      `response` field — system prompt optional
    - generate() raises ModelServerError on HTTP error, timeout,ConnectionError,
      non-JSON body, and HTTP!=200
    - stop() is idempotent: safe on a never-started, already-exited, or
      live process; escalates SIGTERM -> SIGKILL on stubborn subprocesses
    - is_alive() reflects the actual subprocess state

The intent: a future refactor of ModelServer that preserves this contract
must pass these tests unchanged. Integration with a real Ollama is a
separate (manual / CI-gated) test outside this file.
"""

from __future__ import annotations

import socket
import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from workflo_worker.model.model_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_MODEL,
    DEFAULT_STARTUP_TIMEOUT_SECONDS,
    DEFAULT_INFERENCE_TIMEOUT_SECONDS,
    ModelServer,
    ModelServerConfig,
    ModelServerError,
)


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _fake_popen(returncode=None, pid=99999):
    """A MagicMock that quacks like a subprocess.Popen."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.poll.return_value = returncode
    proc.pid = pid
    # terminate/wait/kill should not raise by default
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    return proc


def _port_openish(is_open):
    """Patch `socket.create_connection` so `_is_port_open` returns the
    desired value, while `_wait_ready` immediately succeeds once 'open'."""

    class _FakeSocket:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            if not is_open:
                raise ConnectionRefusedError()
            return self

        def __exit__(self, *a):
            return False

    def _factory(*args, **kwargs):
        return _FakeSocket(*args, **kwargs)

    return _factory


# --------------------------------------------------------------------
# start() lifecycle
# --------------------------------------------------------------------

class TestStartLifecycle:
    def test_start_blocks_until_ready_then_marks_started(self):
        """start() must Popen ollama, wait for readiness, set _started=True."""
        server = ModelServer()

        # _is_port_open returns False initially (nothing listening)
        # _wait_ready sees the port open on the second poll and returns.
        port_open_states = [False, True]

        def fake_socket(*a, **kw):
            class _S:
                def __enter__(self2):
                    if not port_open_states.pop(0):
                        raise ConnectionRefusedError()
                    return self2

                def __exit__(self2, *a2):
                    return False

            return _S()

        with patch("workflo_worker.model.model_server.subprocess.Popen",
                   return_value=_fake_popen()) as mock_popen, \
             patch("workflo_worker.model.model_server.socket.create_connection",
                   side_effect=fake_socket), \
             patch("workflo_worker.model.model_server.time.sleep"):
            server.start()

        assert server._started is True
        assert server.proc is not None
        # Popen call shape: list form, env injected, stdout/stderr DEVNULL,
        # new session so we can SIGTERM the group at teardown.
        args, kwargs = mock_popen.call_args
        assert args[0] == ["ollama", "serve"]
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["start_new_session"] is True
        # OLLAMA_HOST must pin 127.0.0.1 — never 0.0.0.0, even if the caller
        # passed a different host (the executor relies on the localhost bind).
        assert kwargs["env"]["OLLAMA_HOST"] == f"{DEFAULT_HOST}:{DEFAULT_PORT}"
        # Per-request logging is off so prompts don't appear in any log surface.
        assert kwargs["env"]["OLLAMA_DEBUG"] == "0"

    def test_start_rejects_double_call_without_stop(self):
        """Idempotency: calling start() on an already-started server raises."""
        server = ModelServer()
        server._started = True  # simulate a prior start
        with pytest.raises(ModelServerError, match="start\\(\\) called twice"):
            server.start()

    def test_start_raises_when_ollama_binary_missing(self):
        """FileNotFoundError from Popen must surface as ModelServerError."""
        server = ModelServer()
        with patch("workflo_worker.model.model_server.subprocess.Popen",
                   side_effect=FileNotFoundError("ollama: command not found")), \
             patch.object(ModelServer, "_is_port_open", return_value=False):
            with pytest.raises(ModelServerError, match="ollama binary not found"):
                server.start()
        # We failed before assigning proc — state must remain un-started.
        assert server._started is False
        assert server.proc is None

    def test_start_raises_when_port_already_in_use(self):
        """If the port is open and reuse_existing is False, start() fails fast."""
        server = ModelServer(ModelServerConfig(reuse_existing=False))
        with patch.object(ModelServer, "_is_port_open", return_value=True):
            with pytest.raises(ModelServerError, match="Port .* already in use"):
                server.start()
        # Nothing was spawned; state remains clean for a retry.
        assert server._started is False
        assert server.proc is None

    def test_start_adopts_existing_when_reuse_existing_true(self):
        """reuse_existing=True means start() takes the running server as-is."""
        server = ModelServer(ModelServerConfig(reuse_existing=True))
        with patch.object(ModelServer, "_is_port_open", return_value=True), \
             patch("workflo_worker.model.model_server.subprocess.Popen") as mock_popen:
            server.start()
        # No Popen — we adopted the existing process.
        mock_popen.assert_not_called()
        assert server._started is True
        # proc stays None — we don't own the lifecycle of an adopted server.
        assert server.proc is None

    def test_start_kills_subprocess_if_readiness_times_out(self):
        """If _wait_ready raises, start() must kill the spawned process so we
        don't leak a zombie ollama — and re-raise the error."""
        server = ModelServer(ModelServerConfig(startup_timeout_seconds=0.1))

        # Always-closed socket: _wait_ready polls until deadline, then raises.
        def always_closed(*a, **kw):
            class _S:
                def __enter__(self2):
                    raise ConnectionRefusedError()

                def __exit__(self2, *a2):
                    return False

            return _S()

        fake_proc = _fake_popen()
        with patch("workflo_worker.model.model_server.subprocess.Popen",
                   return_value=fake_proc), \
             patch("workflo_worker.model.model_server.socket.create_connection",
                   side_effect=always_closed), \
             patch("workflo_worker.model.model_server.time.sleep"), \
             patch.object(ModelServer, "_is_port_open", return_value=False):
            with pytest.raises(ModelServerError, match="failed to start within"):
                server.start()

        # The zombie was cleaned up: stop() was called internally.
        fake_proc.terminate.assert_called_once()
        # And we never marked ourselves as started.
        assert server._started is False


# --------------------------------------------------------------------
# generate()
# --------------------------------------------------------------------

class TestGenerate:
    # We patch `requests.post` directly (not
    # `workflo_worker.model.model_server.requests.post`) because the
    # model_server module does a local `import requests` inside generate().
    # That local import resolves to the same global `requests` module object
    # regardless of namespace, so patching the module-level attribute is the
    # robust thing to patch.
    _PATCH_TARGET = "requests.post"

    def test_generate_requires_started_state(self):
        """generate() before start() must fail explicitly — never silently."""
        server = ModelServer()
        with pytest.raises(ModelServerError, match="called before start\\(\\)"):
            server.generate("hi")

    def test_generate_returns_response_field(self):
        """A 200 OK with {"response": "..."} must return that field verbatim."""
        server = ModelServer(ModelServerConfig(model="qwen-test"))
        server._started = True

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"response": "hello from model", "extra": "ignored"}
        # resp.textAccessed lazily; provide a benign str.
        fake_resp.text = ""

        with patch(self._PATCH_TARGET,
                   return_value=fake_resp) as mock_post:
            out = server.generate("what is 2+2?")

        assert out == "hello from model"
        # Verify the request shape: correct URL, payload, default timeout.
        args, kwargs = mock_post.call_args
        assert args[0] == f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/api/generate"
        assert kwargs["json"] == {
            "model": "qwen-test",
            "prompt": "what is 2+2?",
            "stream": False,
        }
        assert kwargs["timeout"] == DEFAULT_INFERENCE_TIMEOUT_SECONDS

    def test_generate_passes_system_prompt_when_provided(self):
        """An optional system prompt must be added to the payload as `system`."""
        server = ModelServer()
        server._started = True

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"response": "ok"}
        fake_resp.text = ""

        with patch(self._PATCH_TARGET,
                   return_value=fake_resp) as mock_post:
            server.generate("prompt", system="you are a pylint")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["system"] == "you are a pylint"

    def test_generate_timeout_seconds_override(self):
        """The per-call timeout kwarg overrides the config default."""
        server = ModelServer(ModelServerConfig(inference_timeout_seconds=10.0))
        server._started = True

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"response": "x"}
        fake_resp.text = ""

        with patch(self._PATCH_TARGET,
                   return_value=fake_resp) as mock_post:
            server.generate("p", timeout_seconds=42.0)

        assert mock_post.call_args.kwargs["timeout"] == 42.0

    def test_generate_raises_on_http_timeout(self):
        """requests.Timeout must surface as ModelServerError mentioning timeout."""
        import requests as _requests_mod

        server = ModelServer()
        server._started = True

        with patch(self._PATCH_TARGET,
                   side_effect=_requests_mod.Timeout("slow")):
            with pytest.raises(ModelServerError, match="timed out"):
                server.generate("p")

    def test_generate_raises_on_connection_error(self):
        """ConnectionError (server died mid-call) -> ModelServerError."""
        import requests as _requests_mod

        server = ModelServer()
        server._started = True

        with patch(self._PATCH_TARGET,
                   side_effect=_requests_mod.ConnectionError("refused")):
            with pytest.raises(ModelServerError, match="connection error"):
                server.generate("p")

    def test_generate_raises_on_other_request_exception(self):
        """Any other requests.* exception -> ModelServerError."""
        import requests as _requests_mod

        server = ModelServer()
        server._started = True

        with patch(self._PATCH_TARGET,
                   side_effect=_requests_mod.RequestException("weird")):
            with pytest.raises(ModelServerError, match="HTTP error"):
                server.generate("p")

    def test_generate_raises_on_non_200_status(self):
        """Non-200 HTTP -> ModelServerError with the status + body excerpt."""
        server = ModelServer()
        server._started = True

        fake_resp = MagicMock()
        fake_resp.status_code = 500
        fake_resp.text = "internal server error happened"

        with patch(self._PATCH_TARGET,
                   return_value=fake_resp):
            with pytest.raises(ModelServerError, match="HTTP 500"):
                server.generate("p")

    def test_generate_raises_on_non_json_body(self):
        """200 OK with a non-JSON body -> ModelServerError mentioning non-JSON."""
        server = ModelServer()
        server._started = True

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        # Trigger ValueError on .json() (the path used in the source).
        fake_resp.json.side_effect = ValueError("not json")
        fake_resp.text = "<html>"

        with patch(self._PATCH_TARGET,
                   return_value=fake_resp):
            with pytest.raises(ModelServerError, match="non-JSON"):
                server.generate("p")


# --------------------------------------------------------------------
# stop() and is_alive()
# --------------------------------------------------------------------

class TestStopAndIsAlive:
    def test_stop_on_never_started_is_noop(self):
        """stop() before start() must not raise and leaves state clean."""
        server = ModelServer()
        # Nothing should blow up.
        server.stop()
        assert server._started is False
        assert server.proc is None

    def test_stop_on_already_exited_process_is_noop(self):
        """stop() on a proc that already exited must reset state, no kill."""
        server = ModelServer()
        # proc.poll() returns 0 — process already gone.
        proc = _fake_popen(returncode=0)
        server.proc = proc
        server._started = True

        server.stop()

        proc.terminate.assert_not_called()
        assert server.proc is None
        assert server._started is False

    def test_stop_terminates_then_waits(self):
        """A live process: SIGTERM, wait for exit, reset state."""
        server = ModelServer()
        proc = _fake_popen(returncode=None)
        server.proc = proc
        server._started = True

        server.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5.0)
        proc.kill.assert_not_called()
        assert server.proc is None
        assert server._started is False

    def test_stop_escalates_to_kill_on_timeout(self):
        """If SIGTERM doesn't take, escalate to SIGKILL — never leak."""
        server = ModelServer()
        proc = _fake_popen(returncode=None)
        # First wait (after terminate) times out:
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ollama", timeout=5.0), 0]
        server.proc = proc
        server._started = True

        server.stop()

        proc.terminate.assert_called_once()
        # Two waits: first one (after term) times out, second one (after kill).
        assert proc.wait.call_count == 2
        proc.kill.assert_called_once()
        assert server.proc is None
        assert server._started is False

    def test_stop_handles_processlookuperror_during_terminate(self):
        """If the process vanishes between poll() and terminate(), stop()
        catches ProcessLookupError and still leaves us clean."""
        server = ModelServer()
        proc = _fake_popen(returncode=None)
        proc.terminate.side_effect = ProcessLookupError("gone already")
        server.proc = proc
        server._started = True

        server.stop()

        assert server.proc is None
        assert server._started is False

    def test_is_alive_false_when_no_proc(self):
        server = ModelServer()
        assert server.is_alive() is False

    def test_is_alive_reflects_poll(self):
        server = ModelServer()
        # poll() returns None while the process is running
        proc = _fake_popen(returncode=None)
        server.proc = proc
        assert server.is_alive() is True

        # poll() returns a returncode once exited
        proc.poll.return_value = 0
        assert server.is_alive() is False


# --------------------------------------------------------------------
# config + base_url
# --------------------------------------------------------------------

class TestConfig:
    def test_defaults_present(self):
        """The defaults exported are the ones the Dockerfile.deep + executor
        both depend on — changing one without the other is a silent breakage."""
        assert DEFAULT_HOST == "127.0.0.1"
        assert DEFAULT_PORT == 11434
        assert "qwen2.5-coder" in DEFAULT_MODEL
        assert DEFAULT_STARTUP_TIMEOUT_SECONDS > 0
        assert DEFAULT_INFERENCE_TIMEOUT_SECONDS > 0

    def test_base_url_built_from_host_port(self):
        cfg = ModelServerConfig(host="127.0.0.1", port=11434)
        server = ModelServer(cfg)
        assert server.base_url == "http://127.0.0.1:11434"

        cfg2 = ModelServerConfig(host="localhost", port=9999)
        assert ModelServer(cfg2).base_url == "http://localhost:9999"

    def test_default_config_when_none_passed(self):
        """ModelServer(None) must use the dataclass defaults, not blow up."""
        server = ModelServer(None)
        assert server.config.model == DEFAULT_MODEL
        assert server.config.host == DEFAULT_HOST
        assert server.config.port == DEFAULT_PORT
