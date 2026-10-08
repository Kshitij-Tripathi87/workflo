from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from app.connectors.datahub.client import DataHubClient
from app.services.graph_builder import build_snapshot
from app.engine.future_search_engine import generate_futures
from app.engine.policy import (
    Policy,
    evaluate_policies,
    combine_verdict,
)
from app.models.future import PolicyResultSummary
from app.connectors import list_connectors, get_connector
from app.middleware.auth import get_current_user, require_role
from app.core.auth import User
from app.core.exceptions import CortexError

router = APIRouter(prefix="/future-search", tags=["future-search"])

client = DataHubClient()


class FutureSearchRequest(BaseModel):
    """Request to run future search on an asset.

    `connector` selects the data source for the graph snapshot:
        - "datahub"   (default) — uses the existing sync DataHubClient
        - "dbt"       — parses dbt manifest.json/catalog.json
        - "snowflake" — queries Snowflake INFORMATION_SCHEMA

    Any connector other than "datahub" bypasses `graph_builder` and
    asks the registered connector for a GraphSnapshot directly.
    """

    asset_urn: str
    objective: str = "minimize incident risk"
    constraints: Dict = Field(default_factory=dict)
    policies: Optional[List[Policy]] = None
    connector: str = "datahub"


async def _build_snapshot_for_connector(
    connector_name: str,
    asset_urns: list[str],
):
    """Dispatch to the right snapshot builder based on connector name.

    Returns a GraphSnapshot. Raises HTTPException on unknown connector
    or connector-side errors.
    """
    if connector_name == "datahub":
        return build_snapshot(asset_urns)

    if not list_connectors():
        # Force registry population if connectors weren't imported yet.
        import app.connectors  # noqa: F401

    try:
        conn = get_connector(connector_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        return await conn.build_snapshot(asset_urns)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{connector_name}' misconfigured: {e}",
        )
    except (KeyError, RuntimeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{connector_name}' error: {e}",
        )


@router.post("/run")
async def run_future_search(
    payload: FutureSearchRequest,
    user: User = Depends(require_role("analyst")),
):
    """Generate candidate futures, evaluate policies, return the plan.

    If `policies` are provided, they are evaluated against the ranked
    choice and the verdict is returned as `policy_result.verdict`
    ("pass", "warn", or "block").
    """
    if not payload.asset_urn:
        raise HTTPException(status_code=400, detail="asset_urn is required")

    try:
        snapshot = await _build_snapshot_for_connector(
            payload.connector, [payload.asset_urn]
        )

        if payload.asset_urn not in snapshot.nodes:
            raise HTTPException(status_code=404, detail="Asset not found in graph")

        plan = generate_futures(
            snapshot=snapshot,
            asset_urn=payload.asset_urn,
            objective=payload.objective,
            constraints=payload.constraints,
        )

        if payload.policies:
            policies = list(payload.policies)
            results = evaluate_policies(
                policies=policies,
                severity=plan.ranked_choice.predicted_severity,
                blast_radius=plan.ranked_choice.predicted_blast_radius,
                has_owner=bool(snapshot.nodes[payload.asset_urn].owner),
            )
            verdict = combine_verdict(results)
            plan.policy_result = PolicyResultSummary(
                verdict=verdict,
                results=[r.model_dump() for r in results],
            )

        # Generate tamper-evident cryptographic receipt with teardown proof
        from app.core.receipts import receipt_engine
        plan.receipt = receipt_engine.create_and_sign_receipt(
            action_type="future_search",
            asset_urn=payload.asset_urn,
            parameters={
                "objective": payload.objective,
                "connector": payload.connector,
                "policies_count": len(payload.policies or []),
            },
            result_summary={
                "candidates_count": len(plan.candidates),
                "ranked_choice_severity": plan.ranked_choice.predicted_severity,
                "ranked_choice_blast_radius": plan.ranked_choice.predicted_blast_radius,
                "verdict": plan.policy_result.verdict if plan.policy_result else "pass",
            },
            soc2_controls=["CC6.1", "CC7.2"],
        )

        return plan

    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Asset not found: {e}")
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@router.get("/connectors")
def get_available_connectors(user: User = Depends(get_current_user)):
    """List the connectors currently registered in the running process."""
    import app.connectors  # noqa: F401 - ensure all registered

    return {"connectors": list_connectors()}


@router.get("/{plan_id}")
def get_future_plan(plan_id: str, user: User = Depends(require_role("viewer"))):
    """Get a future plan by ID (placeholder - plans are stateless in v1)."""
    raise HTTPException(
        status_code=404,
        detail="Future plans are stateless in v1 - use POST /future-search/run"
    )
