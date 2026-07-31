"""Parser for dbt manifest.json + catalog.json (v8+ / dbt 1.0+).

Builds the in-memory representation that the connector uses to
construct AssetNode objects and GraphSnapshot. Only the subset of
fields we need is parsed; everything else is ignored.

Key manifest sections used:
- metadata                (version, project_name, generated_at)
- nodes.<model_id>         (name, resource_type, depends_on, config)
  - resource_type == 'model'    -> AssetNode(kind='dataset')
  - resource_type == 'seed'     -> AssetNode(kind='dataset', tags=['seed'])
  - resource_type == 'snapshot'  -> AssetNode(kind='dataset', tags=['snapshot'])
- nodes.<source_id>        (name, source_name, identifier) - external sources
- child_map               (downstream deps keyed by node id)

Catalog sections:
- nodes.<id>.columns.{name}.type  (column TYPES only; manifest has names)
"""
import json
from pathlib import Path
from typing import Any

from app.models.asset import AssetNode, GraphEdge, GraphSnapshot


MODEL_PREFIX = "model."
SOURCE_PREFIX = "source."
SEED_PREFIX = "seed."
SNAPSHOT_PREFIX = "snapshot."


def _urn_for_node(node_id: str, raw: dict) -> str:
    """Build a Cortex URN for a dbt node id."""
    if node_id.startswith(MODEL_PREFIX):
        project = raw.get("package_name") or raw.get("package") or "dbt_project"
        return f"urn:dbt:model:{project}:{raw.get('name', node_id)}"
    if node_id.startswith(SOURCE_PREFIX):
        src = raw.get("source_name", "external")
        name = raw.get("name", raw.get("identifier", node_id))
        return f"urn:dbt:source:{src}:{name}"
    if node_id.startswith(SEED_PREFIX):
        project = raw.get("package_name") or "dbt_project"
        return f"urn:dbt:seed:{project}:{raw.get('name', node_id)}"
    if node_id.startswith(SNAPSHOT_PREFIX):
        project = raw.get("package_name") or "dbt_project"
        return f"urn:dbt:snapshot:{project}:{raw.get('name', node_id)}"
    return f"urn:dbt:node:{node_id}"


def _kind_for(raw: dict) -> str:
    rt = raw.get("resource_type", "model")
    if rt in ("model", "seed", "snapshot"):
        return "dataset"
    return "dataset"


def _tags_for(raw: dict) -> list[str]:
    tags: list[str] = []
    rt = raw.get("resource_type")
    if rt == "seed":
        tags.append("seed")
    elif rt == "snapshot":
        tags.append("snapshot")
    config = raw.get("config") or {}
    mat = config.get("materialized")
    if mat:
        tags.append(f"materialized:{mat}")
    for t in raw.get("tags", []) or []:
        if t not in tags:
            tags.append(t)
    return tags


def parse_manifest(manifest_path: Path) -> tuple[dict[str, AssetNode], list[GraphEdge]]:
    """Parse a dbt manifest.json and return nodes + edges.

    Args:
        manifest_path: Absolute path to manifest.json.

    Returns:
        (nodes_by_urn, edges) where nodes_by_urn maps our URN scheme
        to AssetNode, and edges is a list of GraphEdge objects.
    """
    if not manifest_path or not Path(manifest_path).exists():
        return {}, []

    data = _load_json(manifest_path)
    nodes_raw = data.get("nodes", {})
    sources_raw = data.get("sources", {})
    child_map = data.get("child_map", {})
    parent_map = data.get("parent_map", {})

    nodes_by_id: dict[str, AssetNode] = {}
    urn_by_id: dict[str, str] = {}

    # Models, seeds, snapshots
    for node_id, raw in nodes_raw.items():
        if not raw.get("resource_type") in ("model", "seed", "snapshot"):
            continue
        urn = _urn_for_node(node_id, raw)
        urn_by_id[node_id] = urn
        nodes_by_id[node_id] = AssetNode(
            urn=urn,
            name=raw.get("name", node_id),
            kind=_kind_for(raw),
            owner=raw.get("meta", {}).get("owner"),
            description=raw.get("description") or None,
            schema_fields=_column_names(raw),
            upstream=[],  # filled in below
            downstream=[],
            tags=_tags_for(raw),
            criticality="medium",
            status="active" if raw.get("resource_type") == "model" else None,
        )

    # Sources (external inputs - tables not built by dbt)
    for src_id, raw in sources_raw.items():
        urn = _urn_for_node(src_id, raw)
        urn_by_id[src_id] = urn
        nodes_by_id[src_id] = AssetNode(
            urn=urn,
            name=raw.get("name", src_id),
            kind="dataset",
            description=raw.get("description") or None,
            schema_fields=_column_names(raw),
            upstream=[],
            downstream=[],
            tags=["source"],
            criticality="medium",
        )

    # Build upstream/downstream from parent/child maps
    for node_id, node in nodes_by_id.items():
        parents = parent_map.get(node_id, []) or []
        for parent_id in parents:
            parent = nodes_by_id.get(parent_id)
            if parent:
                node.upstream.append(parent.urn)

        children = child_map.get(node_id, []) or []
        for child_id in children:
            if child_id in nodes_by_id:
                node.downstream.append(urn_by_id[child_id])

    # Build edges
    edges: list[GraphEdge] = []
    for node_id, node in nodes_by_id.items():
        for upstream_urn in node.upstream:
            edges.append(
                GraphEdge(
                    source=upstream_urn,
                    target=node.urn,
                    edge_type="downstream_of",
                    confidence=0.95,
                )
            )

    nodes_by_urn: dict[str, AssetNode] = {n.urn: n for n in nodes_by_id.values()}
    return nodes_by_urn, edges


def parse_catalog(catalog_path: Path, nodes_by_urn: dict[str, AssetNode]) -> None:
    """Enrich AssetNodes with column types from catalog.json. Mutates in place."""
    if not catalog_path or not Path(catalog_path).exists():
        return

    data = _load_json(catalog_path)
    catalog_nodes = data.get("nodes", {})

    # Build a reverse lookup: dbt node name -> AssetNode (for matching)
    name_to_node: dict[str, AssetNode] = {n.name: n for n in nodes_by_urn.values()}

    for cat_id, cat_node in catalog_nodes.items():
        cat_name = cat_node.get("name")
        target = name_to_node.get(cat_name)
        if not target:
            continue
        # If we already have schema_fields (from manifest), keep them.
        # Otherwise, build them from the catalog's columns dict.
        if not target.schema_fields and cat_node.get("columns"):
            target.schema_fields = list(cat_node["columns"].keys())


def _column_names(raw: dict) -> list[str]:
    """Extract column names from a manifest node."""
    cols = raw.get("columns")
    if isinstance(cols, dict):
        return list(cols.keys())
    return []


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def build_snapshot_from_dbt(
    manifest_path: Path,
    catalog_path: Path | None,
    center_urns: list[str],
) -> GraphSnapshot:
    """Convenience helper: parse manifest + catalog, return a
    GraphSnapshot that includes the requested centers plus their
    immediate upstream + downstream neighbors.
    """
    nodes_by_urn, edges = parse_manifest(manifest_path)
    if catalog_path:
        parse_catalog(catalog_path, nodes_by_urn)

    # Resolve the active neighbor set (centers + their immediate neighbors)
    active_urns: set[str] = set()
    for center in center_urns:
        node = nodes_by_urn.get(center)
        if not node:
            continue
        active_urns.add(center)
        active_urns.update(node.upstream)
        active_urns.update(node.downstream)

    active_nodes: dict[str, AssetNode] = {
        urn: nodes_by_urn[urn] for urn in active_urns if urn in nodes_by_urn
    }
    active_edges: list[GraphEdge] = [
        e for e in edges if e.source in active_urns and e.target in active_urns
    ]

    return GraphSnapshot(nodes=active_nodes, edges=active_edges)
