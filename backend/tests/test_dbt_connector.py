"""Tests for the dbt connector: manifest.json parsing + snapshot building."""
import asyncio
from pathlib import Path

import pytest

from app.connectors.dbt.connector import DbtConnector
from app.connectors.dbt.parser import parse_manifest, build_snapshot_from_dbt
from app.connectors.registry import get_connector, is_registered
from app.models.asset import GraphSnapshot


FIXTURE = Path(__file__).parent / "fixtures" / "dbt_manifest.json"


def test_registry_includes_dbt():
    """Importing app.connectors registers the dbt connector automatically."""
    import app.connectors  # noqa: F401

    assert is_registered("dbt")


def test_parse_manifest_returns_five_models_and_two_sources():
    """The fixture has 5 models + 2 sources = 7 nodes total."""
    nodes_by_urn, edges = parse_manifest(FIXTURE)

    assert len(nodes_by_urn) == 7  # 5 models + 2 sources

    node_names = {n.name for n in nodes_by_urn.values()}
    assert "stg_orders" in node_names
    assert "stg_customers" in node_names
    assert "orders" in node_names
    assert "customer_ltv" in node_names
    assert "dashboard_feed" in node_names
    assert "orders" in {n.name for n in nodes_by_urn.values() if "source" in n.tags}

    # 7 directed edges:
    #   source -> stg_orders (1)
    #   source -> stg_customers (1)
    #   stg_orders -> orders (1)
    #   stg_customers -> orders (1)
    #   stg_customers -> customer_ltv (1)
    #   orders -> dashboard_feed (1)
    #   customer_ltv -> dashboard_feed (1)
    assert len(edges) == 7


def test_parse_manifest_urns_match_scheme():
    """Each urn follows urn:dbt:model:<project>:<name> or urn:dbt:source:<src>:<name>."""
    nodes_by_urn, _ = parse_manifest(FIXTURE)

    for urn, node in nodes_by_urn.items():
        if "model" in node.tags or not node.tags:
            # model-style nodes - check urn prefix
            assert (
                urn.startswith("urn:dbt:model:")
                or urn.startswith("urn:dbt:source:")
                or urn.startswith("urn:dbt:seed:")
            ), f"unexpected urn: {urn}"
        else:
            assert urn.startswith("urn:dbt:")


def test_orders_model_has_two_upstream_and_one_downstream():
    """The `orders` model depends on stg_orders + stg_customers and has 1 child."""
    nodes_by_urn, _ = parse_manifest(FIXTURE)

    orders_urn = next(u for u, n in nodes_by_urn.items() if n.name == "orders")
    orders = nodes_by_urn[orders_urn]

    assert len(orders.upstream) == 2
    assert len(orders.downstream) == 1
    # The single downstream should be dashboard_feed
    downstream_node = nodes_by_urn[orders.downstream[0]]
    assert downstream_node.name == "dashboard_feed"


def test_stg_customers_has_two_children():
    """stg_customers feeds both `orders` and `customer_ltv`."""
    nodes_by_urn, _ = parse_manifest(FIXTURE)
    stg_urn = next(u for u, n in nodes_by_urn.items() if n.name == "stg_customers")
    stg = nodes_by_urn[stg_urn]
    assert len(stg.downstream) == 2


def test_build_snapshot_centers_only_includes_neighbors():
    """Snapshot for `orders` should include orders + upstream + downstream = 4 nodes."""
    snapshot = asyncio.run(
        build_snapshot_from_dbt(FIXTURE, None, ["urn:dbt:model:jaffle_shop:orders"])
    )
    assert isinstance(snapshot, GraphSnapshot)
    # centers: 1 (orders)
    # upstream: 2 (stg_orders, stg_customers)
    # downstream: 1 (dashboard_feed)
    # total: 4
    assert len(snapshot.nodes) == 4
    # but stg_customers has another child (customer_ltv) which is NOT in scope
    # because we only traverse 1 hop
    
    names = {n.name for n in snapshot.nodes.values()}
    assert "orders" in names
    assert "stg_orders" in names
    assert "stg_customers" in names
    assert "dashboard_feed" in names
    assert "customer_ltv" not in names  # not a direct neighbor of orders


def test_connector_get_asset_returns_node():
    """DbtConnector.get_asset returns a populated AssetNode."""
    conn = DbtConnector(manifest_path=str(FIXTURE))
    asyncio.run(conn.connect())
    node = asyncio.run(
        conn.get_asset("urn:dbt:model:jaffle_shop:orders")
    )
    assert node.name == "orders"
    assert "order_id" in node.schema_fields
    assert node.owner == "analytics"  # from meta.owner


def test_connector_build_snapshot_returns_graphsnapshot():
    """DbtConnector.build_snapshot returns a usable GraphSnapshot."""
    conn = DbtConnector(manifest_path=str(FIXTURE))
    snapshot = asyncio.run(
        conn.build_snapshot(["urn:dbt:model:jaffle_shop:orders"])
    )
    assert isinstance(snapshot, GraphSnapshot)
    assert "urn:dbt:model:jaffle_shop:orders" in snapshot.nodes


def test_connector_raises_on_missing_manifest(tmp_path):
    """The connector raises FileNotFoundError when the manifest is missing."""
    conn = DbtConnector(manifest_path=str(tmp_path / "nonexistent.json"))
    with pytest.raises(FileNotFoundError):
        asyncio.run(conn.connect())


def test_registry_get_connector_returns_dbt_instance():
    """get_connector('dbt') returns a DbtConnector instance."""
    import app.connectors  # noqa: F401

    conn = get_connector("dbt")
    assert isinstance(conn, DbtConnector)


def test_get_asset_raises_on_unknown_urn():
    """get_asset raises KeyError for an unknown URN."""
    conn = DbtConnector(manifest_path=str(FIXTURE))
    asyncio.run(conn.connect())
    with pytest.raises(KeyError):
        asyncio.run(conn.get_asset("urn:dbt:model:nonexistent:model"))
