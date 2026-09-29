"""CLI integration with Workflo supervisor."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from workflo_supervisor.ipc import SupervisorClient
from sandbox_runtime.config import RunConfig, DepMode, RunResult
from sandbox_runtime.supervisor import Supervisor


class SupervisorCLIClient:
    """CLI wrapper for supervisor communication."""

    def __init__(self):
        self.client = SupervisorClient()

    def run(self, config: RunConfig) -> RunResult:
        """Run sandbox via supervisor."""
        # Try supervisor first, fall back to local execution
        try:
            return self._run_via_supervisor(config)
        except (FileNotFoundError, ConnectionError) as e:
            # Supervisor not running - fall back to local execution
            print(f"Supervisor not available ({e}), running locally...")
            return self._run_local(config)

    def _run_via_supervisor(self, config: RunConfig) -> RunResult:
        """Run via supervisor daemon.

        The run method is a STREAMING method: events flow back as they
        happen and the final ("done", {...}) event carries the full run
        result — including the UNSIGNED receipt payload, which the CLI
        signs. The private key never crosses the IPC boundary.
        """
        params = {
            "sandbox_id": config.sandbox_id,
            "repo_url": config.repo_url,
            "repo_path": str(config.repo_path) if config.repo_path else None,
            "commit_sha": config.commit_sha,
            "probe_groups": config.probe_groups,
            "runtime_image": str(config.runtime_image),
            "memory_mb": config.memory_mb,
            "cpu_cores": config.cpu_cores,
            "timeout_seconds": config.timeout_seconds,
            "dep_mode": config.dep_mode.value,
            "evidence_dir": str(config.evidence_dir),
            "start_command": config.start_command,
            "port": config.port,
        }

        result = None
        for event_type, event_data in self.client.stream_events("run", params):
            if event_type == "done":
                result = event_data
                break

        if result is None:
            raise ConnectionError("Supervisor closed the stream before the run finished")

        # Convert result to RunResult
        return RunResult(
            sandbox_id=config.sandbox_id,
            success=result.get("success", False),
            receipt_path=Path(result["receipt_path"]) if result.get("receipt_path") else None,
            error=result.get("error"),
            lifecycle_events=result.get("lifecycle_events", []),
            receipt_payload=result.get("receipt_payload"),
            evidence_dir=Path(result["evidence_dir"]) if result.get("evidence_dir") else None,
            teardown_verified=result.get("teardown_verified", False),
            elapsed_seconds=result.get("elapsed_seconds", 0.0),
        )

    def _run_local(self, config: RunConfig) -> RunResult:
        """Run locally without supervisor (for development)."""
        supervisor = Supervisor(config)
        return asyncio.run(supervisor.run())

    def verify(self, receipt_path: Path, pubkey: Optional[Path] = None,
               evidence_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Verify a receipt.

        Delegates to the supervisor daemon when available; otherwise
        performs full local verification: schema, Ed25519 signature
        (against the local key store or an explicit pubkey), teardown
        claims, canary, and evidence binding.
        """
        try:
            return self.client.call(
                "verify",
                {
                    "receipt_path": str(receipt_path),
                    "pubkey": str(pubkey) if pubkey else None,
                    "evidence_dir": str(evidence_dir) if evidence_dir else None,
                },
            )
        except (FileNotFoundError, ConnectionError):
            return _verify_receipt_locally(receipt_path, pubkey, evidence_dir)


def _verify_receipt_locally(
    receipt_path: Path,
    pubkey: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Offline receipt verification — no daemon, no control plane.

    Returns {"valid": bool, "checks": [str], "reason": str?}. Fails
    closed on every check that cannot be performed.
    """
    from workflo_schema.sandbox import SignedReceipt
    from sandbox_isolation import (
        verify_receipt_signature,
        verify_evidence_binding,
        resolve_evidence_dir,
    )
    from cryptography.hazmat.primitives import serialization

    checks: list[str] = []

    try:
        data = json.loads(Path(receipt_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"valid": False, "checks": [], "reason": f"cannot read receipt: {e}"}

    receipt_data = data.get("receipt", data)
    try:
        receipt = SignedReceipt(**receipt_data)
    except Exception as e:
        if "UNSUPPORTED_RECEIPT_VERSION" in str(e):
            return {"valid": False, "checks": [],
                    "reason": f"UNSUPPORTED_RECEIPT_VERSION: {e}"}
        return {"valid": False, "checks": [], "reason": f"receipt does not match schema: {e}"}

    # Resolve public key: explicit --pubkey, else local key store
    public_key = None
    if pubkey:
        public_key = serialization.load_pem_public_key(Path(pubkey).read_bytes())
        checks.append(f"loaded public key from {pubkey}")
    elif receipt.public_key_fingerprint:
        key_file = (
            Path.home() / ".config" / "workflo" / "keys"
            / f"{receipt.public_key_fingerprint}.pub.pem"
        )
        if key_file.exists():
            public_key = serialization.load_pem_public_key(key_file.read_bytes())
            checks.append(f"loaded local public key {receipt.public_key_fingerprint}")
        else:
            return {"valid": False, "checks": checks,
                    "reason": f"public key not found at {key_file}"}
    else:
        return {"valid": False, "checks": checks, "reason": "no key to verify against"}

    if not verify_receipt_signature(receipt, public_key):
        return {"valid": False, "checks": checks + ["signature verification failed"],
                "reason": "signature verification failed"}
    checks.append("signature verified")

    # Teardown claims
    tp = receipt.teardown_proof
    if getattr(tp, "runtime_type", None) == "namespaces":
        for name in ("processes_terminated", "cgroup_removed",
                     "network_namespace_removed", "workspace_removed"):
            if getattr(tp, name) is not True:
                return {"valid": False, "checks": checks,
                        "reason": f"teardown claim {name} is {getattr(tp, name)}"}
        checks.append("namespace teardown verified")
    else:
        if not tp.container_removed or not tp.filesystem_removed:
            return {"valid": False, "checks": checks,
                    "reason": "teardown proof shows container/filesystem not removed"}
        checks.append("teardown proof verified")

    # Canary
    if receipt.canary_check.request_succeeded:
        return {"valid": False, "checks": checks, "reason": "canary succeeded — egress was NOT blocked"}
    checks.append("canary confirms egress blocked")

    # Evidence binding
    if receipt.evidence_binding is not None:
        ev_dir = evidence_dir or resolve_evidence_dir(Path(receipt_path), receipt)
        if ev_dir is None:
            return {"valid": False, "checks": checks,
                    "reason": "evidence binding present but evidence directory not found"}
        binding_ok, binding_checks = verify_evidence_binding(receipt, ev_dir)
        checks.extend(binding_checks)
        if not binding_ok:
            return {"valid": False, "checks": checks, "reason": "evidence binding mismatch"}

    return {"valid": True, "checks": checks}


def create_supervisor_client() -> SupervisorCLIClient:
    """Create supervisor CLI client."""
    return SupervisorCLIClient()
