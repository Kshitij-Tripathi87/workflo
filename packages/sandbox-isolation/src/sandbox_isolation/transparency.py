"""Receipt transparency log — append-only store + Merkle inclusion proofs.

SOC 2 CC6.8/CC7.2 and the "verify without trusting us" thesis: a signed
receipt proves the receipt wasn't altered, but says nothing about the
SERVER's behavior after the fact (deleting embarrassing receipts,
rewriting history). An append-only Merkle log closes that gap:

  - Every receipt fingerprint (sha256 of the canonical payload) is appended
    as a leaf. The tree root at size N covers all N leaves; changing or
    dropping ANY past receipt changes every later root.
  - ``proof_inclusion(i)`` returns the sibling-hash path; a verifier with
    the log's checkpoint root can confirm inclusion WITHOUT the server.

Store: ``LocalTransparencyLog`` persists to a JSONL file with atomic
append + fsync. Production ships the file to object storage with retention
lock (S3 Object Lock / WORM) — the FILE is the source of truth, the object
store is the distribution + immutability backstop. The file format is the
contract; swapping the storage driver does not change the cryptography.

Domain separation per RFC 6962:
    leaf_hash(data)  = sha256(0x00 || data)
    node_hash(l, r)  = sha256(0x01 || l || r)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def receipt_fingerprint(canonical_payload: str) -> str:
    """Fingerprint of a receipt's canonical payload — the log leaf value.

    The canonical payload is version-aware (v1 receipts exclude
    receipt_version), so this fingerprint is stable across verifiers for
    every supported receipt version.
    """
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _leaf_hash(leaf_hex: str) -> bytes:
    return hashlib.sha256(_LEAF_PREFIX + bytes.fromhex(leaf_hex)).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


def merkle_root(leaves: list[str], start: int = 0, end: Optional[int] = None) -> bytes:
    """RFC 6962 §2.1 Merkle Tree Hash over the hex leaves [start, end)."""
    if end is None:
        end = len(leaves)
    n = end - start
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return _leaf_hash(leaves[start])
    k = 1 << (n.bit_length() - 1)
    if k == n:  # n is a power of two; split point strictly smaller
        k >>= 1
    return _node_hash(
        merkle_root(leaves, start, start + k),
        merkle_root(leaves, start + k, end),
    )


def _proof_path(leaves: list[str], index: int, start: int, end: int) -> list[str]:
    """RFC 6962 §2.1.1 audit path for leaf ``index`` in leaves[start:end)."""
    n = end - start
    if n == 1:
        return []
    k = 1 << (n.bit_length() - 1)
    if k == n:
        k >>= 1
    if index - start < k:
        return _proof_path(leaves, index, start, start + k) + [
            merkle_root(leaves, start + k, end).hex()
        ]
    return _proof_path(leaves, index, start + k, end) + [
        merkle_root(leaves, start, start + k).hex()
    ]


def verify_inclusion(
    leaf_hex: str, index: int, tree_size: int, proof: list[str], expected_root: str
) -> bool:
    """Verify a Merkle inclusion proof against a checkpoint root.

    The verifier recomputes the root from the leaf + proof; equality with a
    root it independently trusts (e.g. a checkpoint it fetched earlier)
    proves the leaf existed in that tree. The fold mirrors _proof_path:
    splits are derived top-down from (index, tree_size), proof elements
    apply bottom-up, one per level. A proof with the wrong element count
    cannot fold to the right root — counted explicitly.
    """
    if index < 0 or index >= tree_size:
        return False

    # Top-down split sides: True = our leaf was in the LEFT subtree.
    sides: list[bool] = []
    n, g = tree_size, index
    while n > 1:
        k = 1 << (n.bit_length() - 1)
        if k == n:
            k >>= 1
        if g < k:
            sides.append(True)
            n = k
        else:
            sides.append(False)
            g -= k
            n = n - k

    if len(proof) != len(sides):
        return False

    acc = _leaf_hash(leaf_hex)
    for sibling_hex, we_are_left in zip(proof, reversed(sides)):
        sibling = bytes.fromhex(sibling_hex)
        acc = _node_hash(acc, sibling) if we_are_left else _node_hash(sibling, acc)
    return acc.hex() == expected_root


@dataclass(frozen=True)
class LogRecord:
    """One append to the log: the leaf plus the checkpoint it produced."""

    seq: int
    leaf_sha256: str  # receipt fingerprint
    tree_size: int
    root_sha256: str  # root covering leaves [0, seq]
    appended_at: str


class LocalTransparencyLog:
    """Append-only JSONL-backed Merkle log (one file, fsynced per append).

    Thread-safe within a process. The file is append-only BY CONSTRUCTION:
    records are never rewritten; a reader recomputing any checkpoint root
    from leaves detects truncation or mutation.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._leaves: list[str] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            self._leaves.append(record["leaf_sha256"])
        # Verify the last checkpoint on load — a tampered history fails fast
        if self._leaves:
            last = json.loads(self.path.read_text(encoding="utf-8").splitlines()[-1])
            expected = merkle_root(self._leaves).hex()
            if last["root_sha256"] != expected or last["tree_size"] != len(self._leaves):
                raise ValueError(
                    "transparency log failed integrity check: checkpoint root "
                    "does not match recomputed leaves — history was altered"
                )

    @property
    def tree_size(self) -> int:
        return len(self._leaves)

    def checkpoint_root(self) -> str:
        return merkle_root(self._leaves).hex()

    def append(self, leaf_sha256: str) -> LogRecord:
        """Append a receipt fingerprint. Returns the checkpoint record."""
        from datetime import datetime, timezone

        with self._lock:
            self._leaves.append(leaf_sha256)
            record = LogRecord(
                seq=len(self._leaves) - 1,
                leaf_sha256=leaf_sha256,
                tree_size=len(self._leaves),
                root_sha256=merkle_root(self._leaves).hex(),
                appended_at=datetime.now(timezone.utc).isoformat(),
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic append: O_APPEND write + fsync. No truncation path
            # exists anywhere in this class.
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.__dict__, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return record

    def leaf_index(self, leaf_sha256: str) -> Optional[int]:
        try:
            return self._leaves.index(leaf_sha256)
        except ValueError:
            return None

    def proof_inclusion(self, leaf_sha256: str) -> Optional[dict]:
        """Return an inclusion proof for a leaf, or None if absent."""
        index = self.leaf_index(leaf_sha256)
        if index is None:
            return None
        return {
            "leaf_index": index,
            "tree_size": len(self._leaves),
            "root": merkle_root(self._leaves).hex(),
            "proof": _proof_path(self._leaves, index, 0, len(self._leaves)),
        }
