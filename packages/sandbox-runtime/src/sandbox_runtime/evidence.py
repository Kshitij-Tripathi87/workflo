"""Evidence collector - JSONL event ledger + manifest."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class EventRecord:
    """Single event in the ledger."""
    event_id: str
    timestamp: str
    event_type: str
    data: dict
    prev_hash: str
    event_hash: str


@dataclass
class EvidenceManifest:
    """Manifest with hashes for verification."""
    run_id: str
    sandbox_id: str
    started_at: str
    completed_at: str | None
    events_count: int
    events_sha256: str
    logs_sha256: str
    http_traces_sha256: str
    filesystem_changes_sha256: str
    bundle_sha256: str


def metadata_only_enabled() -> bool:
    """Whether retained evidence must contain metadata rather than payload text."""
    return os.environ.get("WORKFLO_EVIDENCE_METADATA_ONLY", "").strip() == "1"


def metadata_only_value(value: Any) -> Any:
    """Replace strings/bytes with length + digest while retaining outcomes/counts."""
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return {"sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded)}
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, dict):
        return {str(key): metadata_only_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [metadata_only_value(child) for child in value]
    return value


class EvidenceCollector:
    """Collects and writes evidence in JSONL format with hash chain."""
    
    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.events_file = evidence_dir / "events.jsonl"
        self.logs_dir = evidence_dir / "logs"
        self.traces_dir = evidence_dir / "traces"
        self.artifacts_dir = evidence_dir / "artifacts"
        
        self._event_counter = 0
        self._prev_hash = "0" * 64
        self._events_hash = hashlib.sha256()
        self._lock = Lock()
        
        # Create directories
        for d in [self.logs_dir, self.traces_dir, self.artifacts_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def write_event(self, event_type: str, data: dict) -> str:
        """Write event to JSONL ledger with hash chain."""
        if metadata_only_enabled():
            data = metadata_only_value(data)
        with self._lock:
            self._event_counter += 1
            event_id = f"evt_{self._event_counter:08d}"
            timestamp = datetime.now(UTC).isoformat()
            
            # Compute event hash
            event_content = f"{event_id}{timestamp}{event_type}{json.dumps(data, sort_keys=True)}{self._prev_hash}"
            event_hash = hashlib.sha256(event_content.encode()).hexdigest()
            
            record = EventRecord(
                event_id=event_id,
                timestamp=timestamp,
                event_type=event_type,
                data=data,
                prev_hash=self._prev_hash,
                event_hash=event_hash
            )
            
            # Write to JSONL
            with open(self.events_file, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
            
            # Update running hash
            self._events_hash.update(event_hash.encode())
            self._prev_hash = event_hash
            
            return event_id
    
    def write_log(self, name: str, content: str) -> str:
        """Write log file and return path."""
        log_path = self.logs_dir / f"{name}.log"
        log_path.write_text(content)
        return str(log_path)
    
    def write_trace(self, name: str, content: bytes) -> str:
        """Write binary trace file and return path."""
        trace_path = self.traces_dir / f"{name}.trace"
        trace_path.write_bytes(content)
        return str(trace_path)
    
    def write_artifact(self, name: str, content: bytes) -> str:
        """Write artifact and return path."""
        artifact_path = self.artifacts_dir / name
        artifact_path.write_bytes(content)
        return str(artifact_path)
    
    def start(self) -> None:
        """Mark collection start."""
        self.write_event("EVIDENCE_STARTED", {"collector_pid": os.getpid()})
    
    def stop(self) -> None:
        """Mark collection end."""
        self.write_event("EVIDENCE_STOPPED", {})

    def redact_retained_payloads(self) -> None:
        """Irreversibly replace workload files with hash/size commitments.

        Called only after every workload and attestation reader has consumed the
        files. The final evidence manifest therefore binds the redacted bundle,
        which remains independently verifiable without retaining source,
        prompts, generated output, logs, or model narrative.
        """
        if not metadata_only_enabled():
            return
        for directory in (self.logs_dir, self.traces_dir, self.artifacts_dir):
            for path in sorted(directory.rglob("*")):
                if not path.is_file():
                    continue
                content = path.read_bytes()
                commitment = {
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                path.write_text(
                    json.dumps(commitment, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    
    def finalize(self, lifecycle_events: list[dict], run_id: str, sandbox_id: str) -> Path:
        """Finalize evidence collection and write manifest."""
        completed_at = datetime.now(UTC).isoformat()
        
        # Calculate final hashes
        events_sha256 = self._events_hash.hexdigest()
        
        # Hash logs directory
        logs_sha256 = _hash_directory(self.logs_dir)
        
        # Hash traces directory
        traces_sha256 = _hash_directory(self.traces_dir)
        
        # Hash artifacts directory
        artifacts_sha256 = _hash_directory(self.artifacts_dir)
        
        # Bundle hash (combination of all)
        bundle_hasher = hashlib.sha256()
        bundle_hasher.update(events_sha256.encode())
        bundle_hasher.update(logs_sha256.encode())
        bundle_hasher.update(traces_sha256.encode())
        bundle_hasher.update(artifacts_sha256.encode())
        bundle_sha256 = bundle_hasher.hexdigest()
        
        # Get start time from first event
        started_at = completed_at
        if self.events_file.exists():
            with open(self.events_file) as f:
                first_line = f.readline().strip()
                if first_line:
                    first_event = json.loads(first_line)
                    started_at = first_event.get("timestamp", completed_at)
        
        manifest = EvidenceManifest(
            run_id=run_id,
            sandbox_id=sandbox_id,
            started_at=started_at,
            completed_at=completed_at,
            events_count=self._event_counter,
            events_sha256=events_sha256,
            logs_sha256=logs_sha256,
            http_traces_sha256=traces_sha256,
            filesystem_changes_sha256=artifacts_sha256,
            bundle_sha256=bundle_sha256,
        )
        
        manifest_path = self.evidence_dir / "manifest.json"
        manifest_path.write_text(json.dumps(asdict(manifest), indent=2))

        return manifest_path

    def build_binding(self) -> dict:
        """Build the evidence binding digests for embedding in a receipt.

        Must be called after finalize(). The returned dict matches the
        workflo_schema EvidenceBinding model: the receipt's Ed25519
        signature covers these digests, binding it to the exact evidence
        ledger produced by this run.
        """
        manifest_path = self.evidence_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("build_binding() called before finalize()")

        manifest = json.loads(manifest_path.read_text())
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        return {
            "evidence_dir": str(self.evidence_dir),
            "events_count": manifest["events_count"],
            "events_sha256": manifest["events_sha256"],
            "bundle_sha256": manifest["bundle_sha256"],
            "manifest_sha256": manifest_sha256,
        }


def _hash_directory(dir_path: Path) -> str:
    """Compute SHA256 of all files in directory."""
    if not dir_path.exists():
        return "0" * 64
    
    hasher = hashlib.sha256()
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def verify_evidence_bundle(evidence_dir: Path) -> bool:
    """Verify evidence bundle integrity."""
    manifest_path = evidence_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    
    with open(manifest_path) as f:
        manifest = json.loads(f.read())
    
    # Verify events.jsonl hash chain
    events_file = evidence_dir / "events.jsonl"
    if not events_file.exists():
        return False
    
    prev_hash = "0" * 64
    events_hasher = hashlib.sha256()
    
    with open(events_file) as f:
        for line in f:
            record = json.loads(line)
            # Verify required fields exist
            required_fields = ["event_id", "timestamp", "event_type", "data", "prev_hash", "event_hash"]
            if not all(field in record for field in required_fields):
                return False
            
            # Verify hash chain
            event_content = f"{record['event_id']}{record['timestamp']}{record['event_type']}{json.dumps(record['data'], sort_keys=True)}{prev_hash}"
            expected_hash = hashlib.sha256(event_content.encode()).hexdigest()
            
            if record["event_hash"] != expected_hash:
                return False
            if record["prev_hash"] != prev_hash:
                return False
            
            events_hasher.update(record["event_hash"].encode())
            prev_hash = record["event_hash"]
    
    if events_hasher.hexdigest() != manifest["events_sha256"]:
        return False
    
    # Verify directory hashes
    if _hash_directory(evidence_dir / "logs") != manifest["logs_sha256"]:
        return False
    if _hash_directory(evidence_dir / "traces") != manifest["http_traces_sha256"]:
        return False
    if _hash_directory(evidence_dir / "artifacts") != manifest["filesystem_changes_sha256"]:
        return False
    
    return True