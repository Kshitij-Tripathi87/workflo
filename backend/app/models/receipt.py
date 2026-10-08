from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class TeardownProof(BaseModel):
    """Evidence of ephemeral teardown for privacy-first execution."""
    sandbox_id: str
    filesystem_wipe_method: str = "tmpfs_umount"
    container_removed: bool = True
    filesystem_removed: bool = True
    no_snapshot_retained: bool = True
    destroyed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_duration_seconds: float = 0.05
    peak_memory_mb: int = 128


class SignedReceipt(BaseModel):
    """Cryptographically verifiable execution receipt."""
    receipt_id: str = Field(description="Unique URI identifier e.g. wf://receipts/...")
    action_type: str = Field(description="impact_analysis | future_search | contract_test | remediation")
    asset_urn: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parameters_hash: str
    result_summary: Dict[str, Any]
    soc2_controls: List[str] = Field(default_factory=lambda: ["CC6.1", "CC7.2"])
    teardown_proof: Optional[TeardownProof] = None
    public_key_fingerprint: Optional[str] = None
    signature: Optional[str] = None

    def canonical_payload(self) -> str:
        """Deterministically format the payload for hashing/signing."""
        payload = {
            "receipt_id": self.receipt_id,
            "action_type": self.action_type,
            "asset_urn": self.asset_urn,
            "timestamp": self.timestamp.isoformat(),
            "parameters_hash": self.parameters_hash,
            "result_summary": self.result_summary,
            "soc2_controls": sorted(self.soc2_controls),
            "public_key_fingerprint": self.public_key_fingerprint or "",
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()


class ReceiptVerificationResponse(BaseModel):
    receipt_id: str
    is_valid: bool
    signer_fingerprint: str
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tamper_detected: bool = False
    message: str
