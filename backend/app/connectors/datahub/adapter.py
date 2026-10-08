from typing import Any, Optional

from app.core.settings import settings
from app.models.asset import AssetNode
from app.connectors.datahub.mock_store import MOCK_ASSETS


class MockDataHubClient:
    def __init__(self, **_kwargs):
        self.base_url = "mock://datahub"
        self.token = "mock-token"

    def get_asset(self, urn: str) -> dict[str, Any]:
        if urn not in MOCK_ASSETS:
            from app.core.exceptions import DataHubNotFoundError

            raise DataHubNotFoundError(urn)
        return MOCK_ASSETS[urn]

    def get_schema(self, urn: str) -> list[str]:
        return self.get_asset(urn).get("schema_fields", [])

    def get_expected_schema(self, urn: str) -> list[str]:
        return self.get_asset(urn).get("expected_schema_fields", [])

    def get_owners(self, urn: str) -> list[str]:
        owner = self.get_asset(urn).get("owner")
        return [owner] if owner else []

    def get_lineage(self, urn: str) -> dict[str, list[str]]:
        asset = self.get_asset(urn)
        return {
            "upstream": asset.get("upstream", []),
            "downstream": asset.get("downstream", []),
        }

    def get_upstream_assets(self, urn: str) -> list[str]:
        return self.get_asset(urn).get("upstream", [])

    def get_downstream_assets(self, urn: str) -> list[str]:
        return self.get_asset(urn).get("downstream", [])

    def get_tags(self, urn: str) -> list[str]:
        return self.get_asset(urn).get("tags", [])

    def get_ml_dependencies(self, urn: str) -> list[str]:
        downstream = self.get_asset(urn).get("downstream", [])
        return [d for d in downstream if d.startswith("urn:li:mlModel:")]

    def get_criticality(self, urn: str) -> str:
        return self.get_asset(urn).get("criticality", "medium")

    def get_freshness(self, urn: str) -> str:
        return self.get_asset(urn).get("freshness", "unknown")

    def get_kind(self, urn: str) -> str:
        return self.get_asset(urn).get("kind", "dataset")

    def get_status(self, urn: str) -> Optional[str]:
        return self.get_asset(urn).get("status")


class DataHubAdapter:
    def __init__(self):
        self._sync_client: Optional[MockDataHubClient] = None
        self._async_client = None

    @property
    def use_mock(self) -> bool:
        return settings.USE_MOCK_DATAHUB or not settings.DATAHUB_BASE_URL

    @property
    def sync(self) -> MockDataHubClient:
        if self._sync_client is None:
            self._sync_client = MockDataHubClient()
        return self._sync_client

    @property
    def async_client(self):
        if self.use_mock:
            return None
        if self._async_client is None:
            from app.connectors.datahub.gms import DataHubGMSClient

            self._async_client = DataHubGMSClient(
                base_url=str(settings.DATAHUB_BASE_URL),
                token=settings.DATAHUB_TOKEN,
            )
        return self._async_client

    async def close(self):
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None


adapter = DataHubAdapter()