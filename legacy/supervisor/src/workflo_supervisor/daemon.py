"""Workflo supervisor daemon - manages sandbox lifecycle."""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
from pathlib import Path

from workflo_supervisor.ipc import SupervisorServer
from sandbox_runtime.supervisor import Supervisor
from sandbox_runtime.config import RunConfig, DepMode


class WorkfloDaemon:
    """Main supervisor daemon."""

    def __init__(self):
        self.server = SupervisorServer()
        self._register_handlers()
        self._running = False
        # Active sandboxes: sandbox_id -> Supervisor (for stop/teardown)
        self._active = {}
        self._active_lock = threading.Lock()

    def _register_handlers(self):
        @self.server.register("health")
        def health(params):
            return {
                "status": "ok",
                "version": "0.1.0",
                "active_sandboxes": list(self._active.keys()),
            }

        @self.server.register_stream("run")
        def run(params):
            return self._handle_run(params)

        @self.server.register("stop")
        def stop(params):
            return self._handle_stop(params)

        @self.server.register("verify")
        def verify(params):
            return self._handle_verify(params)

    def _handle_run(self, params):
        """Handle run request with streaming events.

        Emits ("done", {...}) with the FULL run result including the
        unsigned receipt payload. The daemon never holds a signing key —
        the CLI signs the payload it receives back.
        """
        # Convert params to RunConfig
        config = RunConfig(
            sandbox_id=params.get("sandbox_id"),
            repo_url=params.get("repo_url"),
            repo_path=Path(params["repo_path"]) if params.get("repo_path") else None,
            commit_sha=params.get("commit_sha"),
            probe_groups=params.get("probe_groups", ["surface", "security"]),
            runtime_image=Path(params.get("runtime_image", "/opt/workflo/workflo-worker")),
            memory_mb=params.get("memory_mb", 2048),
            cpu_cores=params.get("cpu_cores", 2.0),
            timeout_seconds=params.get("timeout_seconds", 600),
            dep_mode=DepMode(params.get("dep_mode", "preflight_cache")),
            evidence_dir=Path(params.get("evidence_dir", ".workflo/runs")),
            start_command=params.get("start_command"),
            port=params.get("port"),
        )

        supervisor = Supervisor(config)
        with self._active_lock:
            self._active[config.sandbox_id] = supervisor

        # Run and yield events
        async def run_async():
            result = await supervisor.run()
            yield "done", {
                "success": result.success,
                "receipt_path": str(result.receipt_path) if result.receipt_path else None,
                "receipt_payload": result.receipt_payload,
                "evidence_dir": str(result.evidence_dir) if result.evidence_dir else None,
                "teardown_verified": result.teardown_verified,
                "elapsed_seconds": result.elapsed_seconds,
                "error": result.error,
                "lifecycle_events": result.lifecycle_events,
            }

        # Run async generator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            gen = run_async()
            while True:
                try:
                    event = loop.run_until_complete(gen.__anext__())
                    yield event
                except StopAsyncIteration:
                    break
        finally:
            loop.close()
            with self._active_lock:
                self._active.pop(config.sandbox_id, None)

    def _handle_stop(self, params):
        """Stop a running sandbox: teardown + verification, fail closed."""
        sandbox_id = params.get("sandbox_id")
        if not sandbox_id:
            return {"status": "error", "error": "sandbox_id required"}

        with self._active_lock:
            supervisor = self._active.get(sandbox_id)
        if supervisor is None:
            return {"status": "not_found", "sandbox_id": sandbox_id}

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(supervisor._teardown())
            finally:
                loop.close()
            verification = supervisor.teardown_verification
            return {
                "status": "stopped",
                "sandbox_id": sandbox_id,
                "teardown_verified": bool(verification and verification.all_verified),
                "details": verification.details if verification else {},
            }
        except Exception as e:
            return {"status": "error", "sandbox_id": sandbox_id, "error": str(e)}

    def _handle_verify(self, params):
        """Verify a receipt file: schema, signature, claims, evidence binding.

        The signature is verified against a public key supplied by the
        caller (params["pubkey"] PEM path) or the local key store — the
        daemon holds no public-key directory of its own.
        """
        from workflo_cli.supervisor_client import _verify_receipt_locally

        receipt_path = params.get("receipt_path")
        if not receipt_path:
            return {"valid": False, "reason": "receipt_path required"}

        pubkey = Path(params["pubkey"]) if params.get("pubkey") else None
        evidence_dir = Path(params["evidence_dir"]) if params.get("evidence_dir") else None

        try:
            return _verify_receipt_locally(Path(receipt_path), pubkey, evidence_dir)
        except Exception as e:
            return {"valid": False, "reason": f"verification error: {e}"}

    def start(self):
        """Start the daemon."""
        self._running = True
        self.server.start()

        # Handle signals
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        # Keep running
        import time
        while self._running:
            time.sleep(1)

    def _shutdown(self, signum, frame):
        """Handle shutdown signal."""
        self._running = False
        # Tear down any sandboxes still active — no state survives the daemon.
        with self._active_lock:
            supervisors = list(self._active.values())
        for supervisor in supervisors:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(supervisor._teardown())
                finally:
                    loop.close()
            except Exception:
                pass
        self.server.stop()
        sys.exit(0)


def main():
    """Entry point for workflod."""
    daemon = WorkfloDaemon()
    daemon.start()


if __name__ == "__main__":
    main()
