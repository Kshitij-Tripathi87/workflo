from typing import Any, Dict, List, Optional

from app.connectors.datahub.adapter import adapter


class DataHubClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self._delegate = adapter.sync

    @property
    def base_url(self):
        return self._delegate.base_url

    @property
    def token(self):
        return self._delegate.token

    def get_asset(self, urn: str) -> Dict[str, Any]:
        return self._delegate.get_asset(urn)

    def get_asset_node(self, urn: str) -> Dict[str, Any]:
        return self._delegate.get_asset(urn)

    def get_schema(self, urn: str) -> List[str]:
        return self._delegate.get_schema(urn)

    def get_expected_schema(self, urn: str) -> List[str]:
        return self._delegate.get_expected_schema(urn)

    def get_owners(self, urn: str) -> List[str]:
        return self._delegate.get_owners(urn)

    def get_lineage(self, urn: str) -> Dict[str, List[str]]:
        return self._delegate.get_lineage(urn)

    def get_upstream_assets(self, urn: str) -> List[str]:
        return self._delegate.get_upstream_assets(urn)

    def get_downstream_assets(self, urn: str) -> List[str]:
        return self._delegate.get_downstream_assets(urn)

    def get_tags(self, urn: str) -> List[str]:
        return self._delegate.get_tags(urn)

    def get_ml_dependencies(self, urn: str) -> List[str]:
        return self._delegate.get_ml_dependencies(urn)

    def get_criticality(self, urn: str) -> str:
        return self._delegate.get_criticality(urn)

    def get_freshness(self, urn: str) -> str:
        return self._delegate.get_freshness(urn)

    def get_kind(self, urn: str) -> str:
        return self._delegate.get_kind(urn)

    def get_status(self, urn: str) -> Optional[str]:
        return self._delegate.get_status(urn)