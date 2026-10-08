"""Snowflake connector — implements BaseConnector by querying
INFORMATION_SCHEMA + ACCOUNT_USAGE.

URN scheme:
    urn:snowflake:table:<database>.<schema>.<table_name>
    urn:snowflake:view:<database>.<schema>.<view_name>

Engineers can run this connector in three modes:

1. Real Snowflake connection — set CORTEX_SNOWFLAKE_ACCOUNT/USER/etc.
2. Mock mode (CORTEX_SNOWFLAKE_MOCK=true) — uses a built-in fixture
   so tests and offline demos work without credentials or external
   services.
3. No config at all — `connect()` raises a clear, actionable error.

The `snowflake-connector-python` package is imported lazily so this
module can register itself even when the dep isn't installed.
"""
from typing import Any, Optional

from app.connectors.base import BaseConnector
from app.connectors.registry import register
from app.connectors.snowflake.config import SnowflakeConfig, snowflake_config_from_env
from app.models.asset import AssetNode, GraphEdge, GraphSnapshot


# --- URN helpers ----------------------------------------------------------


def _urn_for(database: str, schema: str, name: str, kind: str) -> str:
    """Build a Cortex URN for a Snowflake table or view."""
    kind_str = "table" if kind.lower() == "base table" else "view"
    return f"urn:snowflake:{kind_str}:{database}.{schema}.{name}"


def _split_urn(urn: str) -> tuple[str, str, str, str]:
    """Parse a Snowflake URN back into (kind, database, schema, name)."""
    parts = urn.split(":", 3)
    if len(parts) != 4:
        raise ValueError(f"Invalid Snowflake URN: {urn}")
    _, _, kind, dotted = parts
    database, schema, name = dotted.rsplit(".", 2)
    return kind, database, schema, name


# --- Mock store (used when mock_mode=True) --------------------------------


MOCK_SNOWFLAKE: dict[str, dict[str, Any]] = {
    "urn:snowflake:table:PROD.PUBLIC.ORDERS": {
        "urn": "urn:snowflake:table:PROD.PUBLIC.ORDERS",
        "name": "ORDERS",
        "kind": "dataset",
        "owner": "data-platform",
        "schema_fields": ["order_id", "customer_id", "amount", "created_at"],
        "upstream": [],
        "downstream": [
            "urn:snowflake:table:PROD.PUBLIC.ORDER_SUMMARY",
            "urn:snowflake:view:PROD.PUBLIC.ORDER_MONITORING",
        ],
        "tags": ["critical", "snowflake"],
        "criticality": "critical",
        "freshness": "fresh",
    },
    "urn:snowflake:table:PROD.PUBLIC.ORDER_SUMMARY": {
        "urn": "urn:snowflake:table:PROD.PUBLIC.ORDER_SUMMARY",
        "name": "ORDER_SUMMARY",
        "kind": "dataset",
        "owner": "analytics",
        "schema_fields": ["order_date", "total_orders", "total_revenue"],
        "upstream": ["urn:snowflake:table:PROD.PUBLIC.ORDERS"],
        "downstream": ["urn:snowflake:view:PROD.PUBLIC.ORDER_MONITORING"],
        "tags": ["snowflake"],
        "criticality": "high",
        "freshness": "fresh",
    },
    "urn:snowflake:view:PROD.PUBLIC.ORDER_MONITORING": {
        "urn": "urn:snowflake:view:PROD.PUBLIC.ORDER_MONITORING",
        "name": "ORDER_MONITORING",
        "kind": "dashboard",
        "owner": "analytics",
        "schema_fields": [],
        "upstream": [
            "urn:snowflake:table:PROD.PUBLIC.ORDERS",
            "urn:snowflake:table:PROD.PUBLIC.ORDER_SUMMARY",
        ],
        "downstream": [],
        "tags": ["snowflake", "looker"],
        "criticality": "high",
        "freshness": "fresh",
    },
}


# --- Connector -----------------------------------------------------------


class SnowflakeConnector(BaseConnector):
    """Connector that reads metadata from Snowflake INFORMATION_SCHEMA.

    Falls back to MOCK_SNOWFLAKE when CORTEX_SNOWFLAKE_MOCK=true or
    when no credentials are configured (so unit tests stay hermetic).
    """

    def __init__(self, config: Optional[SnowflakeConfig] = None):
        self._config = config or snowflake_config_from_env()
        self._conn: Any = None
        self._connected = False
        self._mock_data: dict[str, AssetNode] = {}

    async def connect(self) -> bool:
        cfg = self._config
        if cfg.mock_mode:
            self._mock_data = _build_mock_nodes()
            self._connected = True
            return True

        if not cfg.account or not cfg.user or not cfg.database:
            raise RuntimeError(
                "Snowflake connection requires CORTEX_SNOWFLAKE_ACCOUNT, "
                "CORTEX_SNOWFLAKE_USER, and CORTEX_SNOWFLAKE_DATABASE. "
                "Set CORTEX_SNOWFLAKE_MOCK=true for offline development."
            )

        try:
            import snowflake.connector  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "snowflake-connector-python is not installed. "
                "Install with `pip install cortex[snowflake]` or "
                "`pip install snowflake-connector-python`."
            ) from e

        auth: dict[str, Any] = {"user": cfg.user, "account": cfg.account}
        if cfg.password:
            auth["password"] = cfg.password
        elif cfg.private_key_path:
            with open(cfg.private_key_path, "r") as f:
                auth["private_key"] = f.read()
        else:
            raise RuntimeError(
                "Provide either CORTEX_SNOWFLAKE_PASSWORD or "
                "CORTEX_SNOWFLAKE_PRIVATE_KEY_PATH for authentication."
            )

        self._conn = snowflake.connector.connect(
            warehouse=cfg.warehouse,
            database=cfg.database,
            schema=cfg.schema,
            role=cfg.role,
            **auth,
        )
        self._connected = True
        return True

    async def disconnect(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._connected = False
        self._mock_data.clear()

    async def get_asset(self, urn: str) -> AssetNode:
        if not self._connected:
            await self.connect()

        if self._config.mock_mode:
            if urn not in self._mock_data:
                raise KeyError(f"Snowflake asset not found (mock): {urn}")
            return self._mock_data[urn]

        kind, db, schema, name = _split_urn(urn)
        cols = self._query_columns(db, schema, name)
        owner = self._query_owner(db, schema, name)
        return AssetNode(
            urn=urn,
            name=name,
            kind="dataset",
            owner=owner,
            schema_fields=cols,
            upstream=[],
            downstream=[],  # populated by build_snapshot
            tags=["snowflake"],
            criticality="medium",
        )

    async def get_upstream(self, urn: str) -> list[str]:
        return list((await self.get_asset(urn)).upstream)

    async def get_downstream(self, urn: str) -> list[str]:
        return list((await self.get_asset(urn)).downstream)

    async def build_snapshot(self, center_urns: list[str]) -> GraphSnapshot:
        if not self._connected:
            await self.connect()

        if self._config.mock_mode:
            return _build_mock_snapshot(center_urns)

        # Live path: gather centers + neighbors via ACCOUNT_USAGE
        active_urns: set[str] = set(center_urns)
        for urn in list(center_urns):
            downstream = await self._query_downstream(urn)
            upstream = await self._query_upstream(urn)
            active_urns.update(downstream)
            active_urns.update(upstream)

        nodes: dict[str, AssetNode] = {}
        for urn in active_urns:
            try:
                nodes[urn] = await self.get_asset(urn)
            except (KeyError, ValueError):
                continue

        enriched = await self._enrich_lineage(nodes)
        edges = _edges_from_nodes(enriched)
        return GraphSnapshot(nodes=enriched, edges=edges)

    # --- Live query helpers ------------------------------------------------

    def _query_columns(self, db: str, schema: str, name: str) -> list[str]:
        sql = (
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_CATALOG = %s AND TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION"
        )
        rows = self._execute(sql, (db, schema, name))
        return [r[0] for r in rows]

    def _query_owner(self, db: str, schema: str, name: str) -> Optional[str]:
        sql = (
            "SELECT OWNER FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_CATALOG = %s AND TABLE_SCHEMA = %s AND TABLE_NAME = %s"
        )
        rows = self._execute(sql, (db, schema, name))
        return rows[0][0] if rows else None

    async def _query_downstream(self, urn: str) -> list[str]:
        kind, db, schema, name = _split_urn(urn)
        sql = (
            "SELECT REFERENCED_DATABASE, REFERENCED_SCHEMA, REFERENCED_OBJECT_NAME "
            "FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES "
            "WHERE OBJECT_NAME = %s AND OBJECT_SCHEMA = %s AND OBJECT_DATABASE = %s"
        )
        rows = self._execute(sql, (name, schema, db))
        return [
            f"urn:snowflake:table:{r[0]}.{r[1]}.{r[2]}" for r in rows
        ]

    async def _query_upstream(self, urn: str) -> list[str]:
        kind, db, schema, name = _split_urn(urn)
        sql = (
            "SELECT OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME "
            "FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES "
            "WHERE REFERENCED_OBJECT_NAME = %s "
            "AND REFERENCED_SCHEMA = %s AND REFERENCED_DATABASE = %s"
        )
        rows = self._execute(sql, (name, schema, db))
        return [f"urn:snowflake:table:{r[0]}.{r[1]}.{r[2]}" for r in rows]

    async def _enrich_lineage(self, nodes: dict[str, AssetNode]) -> dict[str, AssetNode]:
        urns = list(nodes.keys())
        for urn in urns:
            upstream = await self._query_upstream(urn)
            downstream = await self._query_downstream(urn)
            nodes[urn].upstream = [u for u in upstream if u in nodes]
            nodes[urn].downstream = [d for d in downstream if d in nodes]
        return nodes

    def _execute(self, sql: str, params: tuple) -> list[tuple]:
        if self._conn is None:
            return []
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()


# --- Mock helpers ---------------------------------------------------------


def _build_mock_nodes() -> dict[str, AssetNode]:
    return {
        urn: AssetNode(**raw) for urn, raw in MOCK_SNOWFLAKE.items()
    }


def _build_mock_snapshot(center_urns: list[str]) -> GraphSnapshot:
    nodes_by_urn = _build_mock_nodes()
    active: set[str] = set(center_urns)
    for center in center_urns:
        node = nodes_by_urn.get(center)
        if node:
            active.update(node.upstream)
            active.update(node.downstream)
    nodes = {urn: nodes_by_urn[urn] for urn in active if urn in nodes_by_urn}
    edges = _edges_from_nodes(nodes)
    return GraphSnapshot(nodes=nodes, edges=edges)


def _edges_from_nodes(nodes: dict[str, AssetNode]) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for node in nodes.values():
        for upstream_urn in node.upstream:
            if upstream_urn in nodes:
                edges.append(
                    GraphEdge(
                        source=upstream_urn,
                        target=node.urn,
                        edge_type="downstream_of",
                        confidence=0.95,
                    )
                )
    return edges


register("snowflake", SnowflakeConnector)
