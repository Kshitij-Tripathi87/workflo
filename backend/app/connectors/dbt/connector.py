"""dbt connector — implements BaseConnector by parsing dbt's
manifest.json + catalog.json. No live database connection required.

URNS:
    urn:dbt:model:<project>:<model_name>
    urn:dbt:source:<source_name>:<table_name>
    urn:dbt:seed:<project>:<seed_name>
    urn:dbt:snapshot:<project>:<snapshot_name>

Snapshots are cached based on file mtime+size so a re-triggered PR with
no manifest changes is served from memory.
"""
from pathlib import Path
from typing import Optional

from app.connectors.base import BaseConnector
from app.connectors.registry import register
from app.connectors.dbt.config import dbt_config_from_env
from app.connectors.dbt.parser import (
    parse_manifest,
    parse_catalog,
    build_snapshot_from_dbt,
)
from app.core.snapshot_cache import get_snapshot_cache, make_cache_key
from app.core.exceptions import ConnectorManifestMissingError
from app.models.asset import AssetNode, GraphSnapshot


def _file_signature(path: Path | None) -> str:
    """Build a content signature from a file's mtime + size."""
    if path is None or not path.exists():
        return "missing"
    stat = path.stat()
    return f"{int(stat.st_mtime)}:{stat.st_size}"


class DbtConnector(BaseConnector):
    """Connector that reads dbt artifacts from disk.

    Instantiation is cheap — it only loads config. Parsing happens in
    `connect()` so that a missing manifest doesn't break imports.
    """

    def __init__(self, manifest_path: Optional[str] = None, catalog_path: Optional[str] = None):
        cfg = dbt_config_from_env()
        self._manifest_path = Path(manifest_path) if manifest_path else cfg["manifest_path"]
        self._catalog_path = Path(catalog_path) if catalog_path else cfg["catalog_path"]
        self._nodes_by_urn: dict[str, AssetNode] = {}
        self._connected = False

    async def connect(self) -> bool:
        if self._manifest_path is None or not self._manifest_path.exists():
            raise ConnectorManifestMissingError(str(self._manifest_path))

        cache = get_snapshot_cache()
        sig = _file_signature(self._manifest_path)
        cache_key = make_cache_key("dbt:nodes", sig)
        cached = cache.get(cache_key)
        if cached is not None:
            self._nodes_by_urn = cached
            self._connected = True
            return True

        nodes_by_urn, _ = parse_manifest(self._manifest_path)
        if self._catalog_path:
            parse_catalog(self._catalog_path, nodes_by_urn)
        self._nodes_by_urn = nodes_by_urn
        cache.set(cache_key, nodes_by_urn)
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self._nodes_by_urn.clear()

    async def get_asset(self, urn: str) -> AssetNode:
        if not self._connected:
            await self.connect()
        if urn not in self._nodes_by_urn:
            raise KeyError(f"dbt asset not found: {urn}")
        return self._nodes_by_urn[urn]

    async def get_upstream(self, urn: str) -> list[str]:
        node = await self.get_asset(urn)
        return list(node.upstream)

    async def get_downstream(self, urn: str) -> list[str]:
        node = await self.get_asset(urn)
        return list(node.downstream)

    async def build_snapshot(self, center_urns: list[str]) -> GraphSnapshot:
        if not self._connected:
            await self.connect()

        cache = get_snapshot_cache()
        manifest_sig = _file_signature(self._manifest_path)
        catalog_sig = _file_signature(self._catalog_path)
        centers_sig = ",".join(sorted(center_urns))
        cache_key = make_cache_key(
            "dbt:snapshot",
            f"{manifest_sig}|{catalog_sig}|{centers_sig}",
        )

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        snapshot = await build_snapshot_from_dbt(
            self._manifest_path,
            self._catalog_path,
            center_urns,
        )
        cache.set(cache_key, snapshot, ttl_seconds=30.0)
        return snapshot


register("dbt", DbtConnector)
