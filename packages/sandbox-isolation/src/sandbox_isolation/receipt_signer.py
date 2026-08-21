"""Receipt signing — Ed25519 signatures over canonical receipt payloads.

Backs Claim #4: "every run produces a signed, tamper-evident receipt."

Ed25519 because:
  - signatures are short (64 bytes) — receipts stay small
  - verification is fast — outside verifier can check in microseconds
  - no key-size decisions to get wrong — unlike RSA
  - widely supported in `cryptography` (the only dep we add for this)

The keypair lives on the Control Plane host, not inside the sandbox. The
sandbox never sees the signing key — it produces a receipt payload, the
executor (outside the sandbox) signs it. This means a compromised sandbox
cannot forge receipts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from workflo_schema.sandbox import SignedReceipt


@dataclass
class ReceiptSigner:
    """Signs and verifies SignedReceipts with an Ed25519 keypair."""

    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_key_fingerprint(self) -> str:
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(raw).hexdigest()

    def sign(self, receipt: SignedReceipt) -> SignedReceipt:
        """Sign the receipt's canonical payload and embed the signature."""

        # Set the fingerprint BEFORE computing canonical payload, so the
        # bytes that get signed include it. verify() recomputes canonical
        # payload with the same fingerprint and must get identical bytes.
        receipt.public_key_fingerprint = self.public_key_fingerprint

        canonical = receipt.canonical_payload().encode("utf-8")
        sig_bytes = self.private_key.sign(canonical)
        receipt.signature = sig_bytes.hex()
        return receipt

    def verify(self, receipt: SignedReceipt) -> bool:
        """Verify a receipt's signature. Used by the Control Plane and by
        the outside-verifier script in Week 7."""

        if not receipt.signature or not receipt.public_key_fingerprint:
            return False

        if receipt.public_key_fingerprint != self.public_key_fingerprint:
            return False

        try:
            sig_bytes = bytes.fromhex(receipt.signature)
            canonical = receipt.canonical_payload().encode("utf-8")
            self.public_key.verify(sig_bytes, canonical)
            return True
        except (InvalidSignature, ValueError):
            return False


def generate_keypair() -> ReceiptSigner:
    """Generate a fresh Ed25519 keypair for a Control Plane instance."""

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return ReceiptSigner(private_key=private_key, public_key=public_key)


def fingerprint_public_key(public_key: Ed25519PublicKey) -> str:
    """SHA-256 fingerprint of a public key, hex-encoded.

    Used to publish a stable identifier for the keypair so outside verifiers
    can fetch the public key by fingerprint and check signatures.
    """

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def verify_receipt_signature(
    receipt: SignedReceipt,
    public_key: Ed25519PublicKey,
) -> bool:
    """Standalone verification — no ReceiptSigner needed.

    This is the function an outside verifier calls. They fetch the public
    key (published by fingerprint) and check the signature on the receipt
    without needing access to the private key.
    """

    if not receipt.signature or not receipt.public_key_fingerprint:
        return False

    expected_fingerprint = fingerprint_public_key(public_key)
    if receipt.public_key_fingerprint != expected_fingerprint:
        return False

    try:
        sig_bytes = bytes.fromhex(receipt.signature)
        canonical = receipt.canonical_payload().encode("utf-8")
        public_key.verify(sig_bytes, canonical)
        return True
    except (InvalidSignature, ValueError):
        return False
