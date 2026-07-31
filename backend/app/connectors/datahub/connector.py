"""Adapts the existing DataHubAdapter (sync/mock-backed) to the
BaseConnector interface, and registers it under the "datahub" name.

This keeps the DataHub connector working with the new connector-aware
API paths while leaving the legacy DataHubClient/Adapter untouched.
"""
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.registry import register
from app.connectors.datahub.client import DataHubClient
from app.connectors.datahub.adapter import adapter as _adapter
from app.models.asset import AssetNode, GraphEdge, GraphSnapshot


_DATAHUB_CLIENT = DataHubClient()


def _asset_dict_to_node(asset: dict[str, Any]) -> AssetNode:
    return AssetNode(
        urn=asset["urn"],
        name=asset["name"],
        kind=asset.get("kind", "dataset"),
        owner=asset.get("owner"),
        description=asset.get("description"),
        schema_fields=asset.get("schema_fields", []),
        upstream=asset.get("upstream", []),
        downstream=asset.get("downstream", []),
        tags=asset.get("tags", []),
        freshness=asset.get("freshness"),
        criticality=asset.get("criticality", "medium"),
        status=asset.get("status"),
    )


def _infer_edge_type(source: AssetNode, target: AssetNode) -> str:
    if target.kind == "model":
        return "trains"
    if target.kind == "dashboard":
        return "powers"
    if source.kind == "pipeline":
        return "feeds"
    return "downstream_of"


class DataHubConnector(BaseConnector):
    """BaseConnector wrapper around the existing sync DataHubClient."""

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        await _adapter.close()

    async def get_asset(self, urn: str) -> AssetNode:
        return _asset_dict_to_node(_DATAHUB_CLIENT.get_asset(urn))

    async def get_upstream(self, urn: str) -> list[str]:
        return _DATAHUB_CLIENT.get_upstream_assets(urn)

    async def get_downstream(self, urn: str) -> list[str]:
        return _DATAHUB_CLIENT.get_downstream_assets(urn)

    async def build_snapshot(self, center_urns: list[str]) -> GraphSnapshot:
        nodes: dict[str, AssetNode] = {}
        edges: list[GraphEdge] = []

        all_urns: set[str] = set(center_urns)
        for urn in center_urns:
            try:
                all_urns.update(_DATAHUB_CLIENT.get_upstream_assets(urn))
                all_urns.update(_DATAHUB_CLIENT.get_downstream_assets(urn))
            except Exception:
                continue

        for urn in all_urns:
            try:
                nodes[urn] = _asset_dict_to_node(_DATAHUB_CLIENT.get_asset(urn))
            except Exception:
                continue

        for urn, node in nodes.items():
            for downstream_urn in node.downstream:
                if downstream_urn in nodes:
                    target = nodes[downstream_urn]
                    edges.append(
                        GraphEdge(
                            source=urn,
                            target=downstream_urn,
                            edge_type=_infer_edge_type(node, target),
                            confidence=0.95,
                        )
                    )
            for upstream_urn in node.upstream:
                if upstream_urn in nodes:
                    edges.append(
                        GraphEdge(
                            source=upstream_urn,
                            target=urn,
                            edge_type="upstream_of",
                            confidence=0.95,
                        )
                    )

        return GraphSnapshot(nodes=nodes, edges=edges)


register("datahub", DataHubConnector)
