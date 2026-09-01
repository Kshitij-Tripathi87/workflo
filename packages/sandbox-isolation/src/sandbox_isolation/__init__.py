"""Airlock sandbox-isolation primitive.

The architectural enforcement of the "we forget it" guarantee. Every piece of
this package exists to make one specific claim hard to violate:

  - ephemeral_fs:   the customer's repo lives on tmpfs, never on disk
  - network_policy: egress is locked down by default, not configured open
  - teardown_proof: post-run checks that container + tmpfs are GONE
  - receipt_signer: Ed25519 signature over the canonical receipt payload

If you're adding code to this package, ask: "does this make the no-retention
guarantee easier or harder to violate?" If easier, don't merge it.
"""

from sandbox_isolation.ephemeral_fs import (
    EphemeralMount,
    mount_tmpfs,
    unmount_tmpfs,
    verify_ephemeral_gone,
)
from sandbox_isolation.network_policy import (
    DEFAULT_BLOCKED_EGRESS,
    build_isolation_args,
    attempt_canary_request,
    CanaryResult,
)
from sandbox_isolation.teardown_proof import (
    verify_container_gone,
    build_teardown_proof,
)
from sandbox_isolation.receipt_signer import (
    ReceiptSigner,
    generate_keypair,
    verify_receipt_signature,
    fingerprint_public_key,
)

__all__ = [
    "EphemeralMount",
    "mount_tmpfs",
    "unmount_tmpfs",
    "verify_ephemeral_gone",
    "DEFAULT_BLOCKED_EGRESS",
    "build_isolation_args",
    "attempt_canary_request",
    "CanaryResult",
    "verify_container_gone",
    "build_teardown_proof",
    "ReceiptSigner",
    "generate_keypair",
    "verify_receipt_signature",
    "fingerprint_public_key",
]

__version__ = "0.1.0"
