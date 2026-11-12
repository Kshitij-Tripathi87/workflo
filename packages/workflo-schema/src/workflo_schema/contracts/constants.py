"""Frozen constants for the v1 contracts."""

from __future__ import annotations

# Contract schema version carried by every frozen model.
SCHEMA_VERSION = "1"

# Receipt protocol.
RECEIPT_VERSION_V5 = 5
DSSE_PAYLOAD_TYPE = "application/vnd.workflo.receipt.v5+json"

# Evidence chain (ADR-0016). The genesis constant matches the TypeScript
# ledger's long-standing value so both implementations anchor identically.
EVIDENCE_CHAIN_VERSION = 2
EVIDENCE_GENESIS_INPUT = "workflo:evidence:genesis:v1"

# Every receipt v5 payload carries a non-empty limitations list. These are
# the frozen baseline claims the receipt does NOT make.
DEFAULT_RECEIPT_LIMITATIONS: tuple[str, ...] = (
    "Does not assert that the repository contains no defects.",
    "Does not assert that every possible execution path was explored.",
    "Does not assert that the AI agent found every meaningful issue.",
    "Does not assert that a malicious guest is impossible to escape.",
    "Does not assert that every external system behaved correctly.",
    "Does not establish factual truth of reported observations; it binds "
    "the identified scope, identity, evidence, and teardown record.",
)
