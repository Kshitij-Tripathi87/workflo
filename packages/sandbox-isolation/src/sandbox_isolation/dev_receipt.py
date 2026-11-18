"""Local development signing and offline verification for receipt v5.

These are not a production signer or a general v5 attestation verifier. The
only accepted profile is the sealed namespace check backed by its full local
bundle and an out-of-band trusted Ed25519 public key.
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from workflo_schema.contracts import (
    DSSE_PAYLOAD_TYPE,
    ComponentVerificationStatus,
    DsseEnvelopeV1,
    DsseSignatureV1,
    EvidenceManifestV1,
    ExecutionStatus,
    QaVerdict,
    ReceiptV5Payload,
    RunOutcomeV1,
    RuntimeIdentityV1,
    RuntimeType,
    SignedReceiptV5,
    SignerIdentityV1,
    SourceProvenanceV1,
    TrustVerificationStatus,
    decode_dsse_payload,
    encode_dsse_payload,
    utc_now_ms,
)

from sandbox_isolation.dev_evidence import DevEvidence, validate_dev_evidence
from sandbox_isolation.receipt_signer import fingerprint_public_key

_LIMITATIONS = (
    "Development namespaces share the host kernel; this is not Firecracker or production isolation evidence.",
    "This attests only to the admitted test file and this run. It does not establish absolute correctness or root cause.",
    "Trust the local operator, runtime image, and reviewed repository and checks. Guest test reports are observations.",
    "The source and runtime digests are host observations; the bundle does not contain those bytes.",
)


def _pre_auth_encoding(payload_type: str, payload: bytes) -> bytes:
    """DSSE PAE, using byte lengths and the protocol's payload type."""
    kind = payload_type.encode("ascii")
    return b"DSSEv1 %d %s %d %s" % (len(kind), kind, len(payload), payload)


def _signer(public_key: Ed25519PublicKey) -> SignerIdentityV1:
    digest = f"sha256:{fingerprint_public_key(public_key)}"
    return SignerIdentityV1(
        signer_id="workflo-local-dev",
        key_id=digest,
        provider="file-dev",
        public_key_fingerprint=digest,
    )


def _receipt_payload(
    evidence: DevEvidence,
    manifest: EvidenceManifestV1,
    finding_digest: str,
    public_key: Ed25519PublicKey,
    issued_at: str,
) -> ReceiptV5Payload:
    if issued_at < evidence.teardown.observed_at:
        raise ValueError("receipt issued before teardown verification")
    spec = evidence.spec
    verified = ComponentVerificationStatus.VERIFIED
    return ReceiptV5Payload(
        **evidence.scope,
        sandbox_id=evidence.sandbox_id,
        receipt_id=f"receipt-{spec.idempotency_key}",
        source=SourceProvenanceV1(
            provider=spec.source.provider,
            ref=spec.source.ref,
            commit=evidence.snapshot.commit,
            snapshot_digest=evidence.snapshot.digest(),
        ),
        execution_policy_digest=spec.policy_digest,
        runtime=RuntimeIdentityV1(
            runtime_type=RuntimeType.NAMESPACES, runtime_image_digest=spec.runtime_image_digest
        ),
        execution_started_at=spec.created_at,
        execution_completed_at=evidence.checks_at,
        outcome=RunOutcomeV1(
            execution_status=ExecutionStatus.COMPLETED,
            qa_verdict=QaVerdict.FAIL if evidence.report.returncode else QaVerdict.PASS,
            trust_status=TrustVerificationStatus.VERIFIED_CLEAN,
            evidence_validation=verified,
            teardown_verification=verified,
            receipt_status=verified,
        ),
        finding_summary_digest=finding_digest,
        evidence_manifest_digest=manifest.digest(),
        evidence_ledger_root=manifest.ledger_root,
        evidence_ledger_checkpoint=manifest.ledger_checkpoint,
        evidence_chain_version=manifest.ledger_chain_version,
        teardown_verification=evidence.teardown,
        limitations=_LIMITATIONS,
        signer_identity=_signer(public_key),
        issued_at=issued_at,
    )


def sign_dev_receipt(
    directory: Path, expected_manifest_digest: str, key: Ed25519PrivateKey
) -> SignedReceiptV5:
    """Sign only after re-reading evidence and matching the host's anchor."""
    evidence, manifest, finding_digest = validate_dev_evidence(directory)
    if manifest.digest() != expected_manifest_digest:
        raise ValueError("evidence does not match the host's finalized manifest")
    payload = _receipt_payload(evidence, manifest, finding_digest, key.public_key(), utc_now_ms())
    encoded = encode_dsse_payload(payload)
    message = _pre_auth_encoding(DSSE_PAYLOAD_TYPE, base64.b64decode(encoded, validate=True))
    signature = key.sign(message)
    key.public_key().verify(signature, message)
    return SignedReceiptV5(
        envelope=DsseEnvelopeV1(
            payload=encoded,
            signatures=(
                DsseSignatureV1(
                    keyid=payload.signer_identity.key_id,
                    sig=base64.b64encode(signature).decode("ascii"),
                ),
            ),
        )
    )


def verify_dev_receipt(
    receipt: SignedReceiptV5, directory: Path, trusted_key: Ed25519PublicKey
) -> ReceiptV5Payload:
    """Validate signature and complete evidence; a verified FAIL is still valid."""
    envelope = receipt.envelope
    payload = decode_dsse_payload(envelope)
    signer = _signer(trusted_key)
    if (
        payload.runtime.runtime_type is not RuntimeType.NAMESPACES
        or payload.signer_identity != signer
    ):
        raise ValueError("wrong trusted key or unsupported development signer/profile")
    if len(envelope.signatures) != 1 or envelope.signatures[0].keyid != signer.key_id:
        raise ValueError("receipt must have one signature from the trusted key")
    if encode_dsse_payload(payload) != envelope.payload:
        raise ValueError("receipt payload is not canonical")
    try:
        trusted_key.verify(
            base64.b64decode(envelope.signatures[0].sig, validate=True),
            _pre_auth_encoding(
                envelope.payload_type, base64.b64decode(envelope.payload, validate=True)
            ),
        )
    except InvalidSignature as exc:
        raise ValueError("receipt signature verification failed") from exc
    evidence, manifest, finding_digest = validate_dev_evidence(directory)
    expected = _receipt_payload(evidence, manifest, finding_digest, trusted_key, payload.issued_at)
    if payload != expected:
        raise ValueError(
            "receipt does not bind this run's source, policy, outcome, evidence and teardown"
        )
    return payload
