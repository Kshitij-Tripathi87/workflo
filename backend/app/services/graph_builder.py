from typing import List
from app.models.asset import AssetNode, GraphEdge, GraphSnapshot
from app.connectors.datahub.client import DataHubClient

client = DataHubClient()


def _asset_to_node(urn: str) -> AssetNode:
    """Convert raw asset dict to AssetNode."""
    asset = client.get_asset(urn)
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
    """Infer edge type based on asset kinds."""
    if target.kind == "model":
        return "trains"
    if target.kind == "dashboard":
        return "powers"
    if source.kind == "pipeline":
        return "feeds"
    return "downstream_of"


def build_snapshot(center_urns: List[str]) -> GraphSnapshot:
    """
    Build a graph snapshot centered around given assets.
    Includes the center assets plus their immediate upstream and downstream neighbors.
    """
    nodes: dict[str, AssetNode] = {}
    edges: List[GraphEdge] = []
    
    # Collect all URNs to include (centers + neighbors)
    all_urns = set(center_urns)
    for urn in center_urns:
        try:
            upstream = client.get_upstream_assets(urn)
            downstream = client.get_downstream_assets(urn)
            all_urns.update(upstream)
            all_urns.update(downstream)
        except KeyError:
            continue
    
    # Load all nodes
    for urn in all_urns:
        try:
            nodes[urn] = _asset_to_node(urn)
        except KeyError:
            continue
    
    # Build edges from lineage relationships
    for urn, node in nodes.items():
        # Downstream edges
        for downstream_urn in node.downstream:
            if downstream_urn in nodes:
                target = nodes[downstream_urn]
                edges.append(GraphEdge(
                    source=urn,
                    target=downstream_urn,
                    edge_type=_infer_edge_type(node, target),
                    confidence=0.95
                ))
        # Upstream edges
        for upstream_urn in node.upstream:
            if upstream_urn in nodes:
                edges.append(GraphEdge(
                    source=upstream_urn,
                    target=urn,
                    edge_type="upstream_of",
                    confidence=0.95
                ))
    
    return GraphSnapshot(nodes=nodes, edges=edges)


def get_subgraph(center_urn: str, depth: int = 2) -> GraphSnapshot:
    """
    Get a subgraph centered on a single asset with specified traversal depth.
    For MVP, depth=1 (immediate neighbors) is used.
    """
    return build_snapshot([center_urn])