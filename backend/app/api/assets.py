from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.models import AssetSummary
from app.connectors.datahub.client import DataHubClient
from app.core.exceptions import CortexError
from app.middleware.auth import require_role
from app.core.auth import User

router = APIRouter(prefix="/assets", tags=["assets"])
client = DataHubClient()


@router.get("/{urn}", response_model=AssetSummary)
def get_asset(urn: str, user: User = Depends(require_role("viewer"))):
    """Get asset summary by URN."""
    try:
        asset = client.get_asset(urn)
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetSummary(
        urn=asset["urn"],
        name=asset["name"],
        description=asset.get("description"),
        owner=asset.get("owner"),
        schema_fields=asset.get("schema_fields", []),
    )


@router.get("/{urn}/lineage")
def get_lineage(urn: str, user: User = Depends(require_role("viewer"))) -> Dict[str, List[str]]:
    """Get upstream and downstream lineage for an asset."""
    try:
        return client.get_lineage(urn)
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.get("/{urn}/graph")
def get_asset_graph(urn: str, user: User = Depends(require_role("viewer"))) -> Dict[str, Any]:
    """Get normalized graph snapshot for an asset."""
    from app.services.graph_builder import build_snapshot

    try:
        asset = client.get_asset(urn)
        snapshot = build_snapshot([urn])

        node = snapshot.nodes.get(urn)
        if not node:
            raise HTTPException(status_code=404, detail="Asset not found")

        return {
            "node": node.model_dump(),
            "edges": [e.model_dump() for e in snapshot.edges],
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges)
        }
    except CortexError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except KeyError:
        raise HTTPException(status_code=404, detail="Asset not found")