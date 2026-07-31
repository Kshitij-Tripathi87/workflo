"""DataHub-native write-back.

Creates incidents, attaches artifacts as documentation, and tags assets
in DataHub via the GMS client.

When USE_MOCK_DATAHUB=true, this writes to the local JSONL log instead.
When a real DataHub is configured, it writes to DataHub GMS and mirrors
the result to JSONL for local debugging.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.core.settings import settings
from app.models.impact import ImpactReport
from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft
from app.models.future import FuturePlan
from app.models.writeback import WritebackRecord
from app.connectors.datahub.adapter import adapter


def _safe_resolve(raw_path, base_dir: Path | None = None) -> Path:
    """Resolve a writeback-path candidate safely.

    Rejects paths that escape the base directory via traversal.  The
    resolved absolute path must be a descendant of the base directory.
    Falls back to base_dir/<basename> when the resolved path escapes.
    """
    base = base_dir or (Path.cwd() / "data")
    try:
        raw_str = str(raw_path)
    except Exception:
        raw_path = Path("writeback.jsonl")
        raw_str = str(raw_path)

    try:
        resolved = Path(raw_str).resolve()
    except (OSError, RuntimeError):
        return base / Path(raw_str).name

    # Ensure the resolved path is within the allowed base directory
    try:
        resolved.relative_to(base)
    except ValueError:
        return base / resolved.name

    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _writeback_path() -> Path:
    return _safe_resolve(settings.WRITEBACK_PATH)


def _mirror_to_jsonl(record: WritebackRecord):
    """Persist a record to the local JSONL log for debugging."""
    with open(_writeback_path(), "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def _build_summary(
    asset_name: str,
    impact: ImpactReport,
    rec: Recommendation,
    plan: Optional[FuturePlan] = None,
) -> str:
    parts = [f"Cortex resolution for {asset_name}."]
    if plan:
        parts.append(
            f"Future search recommended {plan.ranked_choice.scenario_type} "
            f"(severity {plan.ranked_choice.predicted_severity}, "
            f"effort {plan.ranked_choice.predicted_effort}, "
            f"benefit {plan.ranked_choice.predicted_benefit})."
        )
    parts.append(f"Impact severity: {impact.severity}.")
    parts.append(f"Action: {rec.action_type}.")
    return " ".join(parts)


def _build_artifact_doc(artifact: Optional[ArtifactDraft]) -> str:
    """Build a markdown doc from the artifact for DataHub documentation tab."""
    if not artifact:
        return "_No artifact attached._"
    return f"""# Cortex Generated Artifact

**Type:** `{artifact.artifact_type}`
**Confidence:** {artifact.confidence:.0%}

```{artifact.artifact_type}
{artifact.body}
```
"""


def build_verdict_assertion_payload(
    asset_urn: str,
    asset_name: str,
    verdict: str,
    reason: str,
    severity: str,
    blast_radius: int,
    run_id: str,
    created_by: str = "system",
) -> dict:
    """Build a structured assertion payload that mirrors DataHub's assertion schema.

    The payload is designed to be:
      - Persisted to the local JSONL log (always)
      - Written as DataHub tags + documentation (real DataHub)
      - Inspectable from the JSONL for debugging (mock mode)

    Field shape mirrors DataHub's Assertion entity so a downstream
    consumer can interpret the verdict without knowing it came from
    Cortex.
    """
    timestamp = datetime.utcnow().isoformat()
    return {
        "assertion_type": "CORTEX_VERDICT",
        "urn": asset_urn,
        "asset_name": asset_name,
        "verdict": verdict,
        "severity": severity,
        "blast_radius": blast_radius,
        "reason": reason,
        "run_id": run_id,
        "created_by": created_by,
        "timestamp": timestamp,
    }


async def record_verdict_assertion(
    asset_urn: str,
    asset_name: str,
    verdict: str,
    reason: str,
    severity: str = "medium",
    blast_radius: int = 0,
    run_id: Optional[str] = None,
    created_by: str = "system",
) -> dict:
    """Cherry #2 — write back the verdict to DataHub as an assertion.

    Always persists to the JSONL log. When a real DataHub client is
    available, additionally:
      - Adds tags `cortex:assertion-{verdict}`, `cortex:severity-{...}`
      - Appends the verdict to the asset's documentation tab

    This closes the read-write loop with DataHub: the agent READS
    metadata, REASONS about impact, ACTS by blocking, and WRITES
    BACK so future agents or humans see what happened.
    """
    run_id = run_id or str(uuid4())
    payload = build_verdict_assertion_payload(
        asset_urn=asset_urn,
        asset_name=asset_name,
        verdict=verdict,
        reason=reason,
        severity=severity,
        blast_radius=blast_radius,
        run_id=run_id,
        created_by=created_by,
    )

    # Always mirror to JSONL log so the verdict is durable + inspectable
    jsonl_line = json.dumps(
        {
            "kind": "assertion",
            "record_id": run_id,
            "asset_urn": asset_urn,
            "status": verdict,
            "summary": reason,
            "linked_artifact": None,
            "affected_assets": [],
            "created_by": created_by,
            "created_at": payload["timestamp"],
            "payload": payload,
        }
    )
    with open(_writeback_path(), "a", encoding="utf-8") as f:
        f.write(jsonl_line + "\n")

    # Write to real DataHub if a client is available
    client = adapter.async_client
    if client is not None:
        try:
            tags = [
                "cortex:assertion",
                f"cortex:verdict-{verdict}",
                f"cortex:severity-{severity}",
                f"cortex:blast-radius-{blast_radius}",
            ]
            for tag in tags:
                await client.add_tags(asset_urn, [tag])

            doc = (
                f"## Cortex Verdict ({payload['timestamp']})\n\n"
                f"- **Verdict:** `{verdict.upper()}`\n"
                f"- **Severity:** {severity}\n"
                f"- **Blast radius:** {blast_radius} downstream\n"
                f"- **Reason:** {reason}\n"
                f"- **Run ID:** `{run_id}`\n"
            )
            await client.add_documentation(asset_urn, doc)
        except Exception:
            # Already mirrored to JSONL — DataHub failure is non-fatal
            pass

    return payload



async def record_resolution_to_datahub(
    asset_urn: str,
    asset_name: str,
    impact: ImpactReport,
    recommendation: Recommendation,
    artifact: Optional[ArtifactDraft] = None,
    plan: Optional[FuturePlan] = None,
    created_by: str = "system",
) -> WritebackRecord:
    """
    Record a resolution to DataHub (incident + tags + documentation).

    Falls back to JSONL-only when mock mode is active or DataHub is unavailable.
    """
    summary = _build_summary(asset_name, impact, recommendation, plan)
    record = WritebackRecord(
        asset_urn=asset_urn,
        status="triaged",
        summary=summary,
        linked_artifact=artifact.artifact_id if artifact else None,
        affected_assets=impact.affected_assets,
        created_by=created_by,
    )

    client = adapter.async_client
    if client is None:
        # Mock mode - JSONL only
        _mirror_to_jsonl(record)
        return record

    # Real DataHub write-back
    try:
        await client.create_incident(
            {
                "urn": asset_urn,
                "type": "SCHEMA_CHANGE_RISK",
                "title": f"Cortex: {impact.severity} severity on {asset_name}",
                "description": summary,
            }
        )

        await client.add_documentation(
            asset_urn,
            _build_artifact_doc(artifact),
        )

        confidence_pct = int((artifact or recommendation).confidence * 100)
        tags = [
            "cortex:resolved",
            f"cortex:severity-{impact.severity}",
            f"cortex:action-{recommendation.action_type}",
            f"cortex:confidence-{confidence_pct}",
        ]
        if plan:
            tags.append(f"cortex:future-search-{plan.ranked_choice.scenario_type}")
        await client.add_tags(asset_urn, tags)
    except Exception:
        # DataHub failure - still mirror locally and return the record
        _mirror_to_jsonl(record)
    else:
        _mirror_to_jsonl(record)

    return record


# --- Synchronous JSONL writeback (legacy) ---


class WritebackServiceSync:
    """Synchronous JSONL writeback (used by mock mode and existing endpoints)."""

    def __init__(self, base_path: str | None = None):
        from app.connectors.datahub.writeback import _safe_resolve

        raw = base_path or settings.WRITEBACK_PATH
        base_dir = Path(raw).resolve().parent if base_path else None
        self.base_path = _safe_resolve(raw, base_dir=base_dir)
        self.base_path.parent.mkdir(parents=True, exist_ok=True)

    def record_resolution(
        self,
        asset_urn: str,
        impact_report: ImpactReport,
        recommendation: Recommendation,
        artifact: Optional[ArtifactDraft] = None,
        created_by: str = "system",
    ) -> WritebackRecord:
        summary = (
            f"Impact analysis for {asset_urn}: {impact_report.reason} "
            f"Recommended action: {recommendation.action_type}. "
            f"Confidence: {recommendation.confidence:.0%}."
        )
        record = WritebackRecord(
            asset_urn=asset_urn,
            status="triaged",
            summary=summary,
            linked_artifact=artifact.artifact_id if artifact else None,
            affected_assets=impact_report.affected_assets,
            created_by=created_by,
        )
        with open(self.base_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        return record

    def _read_all(self) -> dict[str, dict]:
        """Read the JSONL log and dedupe by record_id, returning latest version."""
        latest: dict[str, dict] = {}
        if not self.base_path.exists():
            return latest
        with open(self.base_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rid = data.get("record_id")
                    if rid:
                        latest[rid] = data
                except (json.JSONDecodeError, ValueError):
                    continue
        return latest

    def _rewrite_all(self, latest: dict[str, dict]) -> None:
        """Atomically rewrite the JSONL file with the dedupe'd records."""
        tmp_path = self.base_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for data in latest.values():
                f.write(json.dumps(data, default=str) + "\n")
        tmp_path.replace(self.base_path)

    def get_resolutions(self, asset_urn: str) -> list[WritebackRecord]:
        latest = self._read_all()
        results: list[WritebackRecord] = []
        for data in latest.values():
            if data.get("asset_urn") == asset_urn:
                try:
                    results.append(WritebackRecord(**data))
                except (ValueError, TypeError):
                    continue
        # Stable order: newest first
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def get_record(self, record_id: str) -> Optional[WritebackRecord]:
        latest = self._read_all()
        data = latest.get(record_id)
        return WritebackRecord(**data) if data else None

    def update_status(self, record_id: str, status: str) -> Optional[WritebackRecord]:
        latest = self._read_all()
        if record_id not in latest:
            return None
        latest[record_id]["status"] = status
        self._rewrite_all(latest)
        return WritebackRecord(**latest[record_id])
