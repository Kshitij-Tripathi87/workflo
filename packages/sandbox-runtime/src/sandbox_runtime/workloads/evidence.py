"""Evidence collector workload - runs as separate process to collect events."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from sandbox_runtime.evidence import EvidenceCollector


async def run_evidence_workload(config, evidence: EvidenceCollector) -> dict:
    """Evidence collector runs throughout the sandbox lifecycle."""
    
    evidence.start()
    
    # The evidence collector is passive - it just provides the API
    # Other workloads call evidence.write_event(), etc.
    # This workload just waits for the sandbox to complete
    
    evidence.write_event("EVIDENCE_WORKLOAD_STARTED", {})
    
    return {"status": "running"}