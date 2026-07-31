from abc import ABC, abstractmethod
from typing import Any

from app.models.asset import AssetNode, GraphSnapshot


class BaseConnector(ABC):
    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def get_asset(self, urn: str) -> AssetNode: ...

    @abstractmethod
    async def get_upstream(self, urn: str) -> list[str]: ...

    @abstractmethod
    async def get_downstream(self, urn: str) -> list[str]: ...

    @abstractmethod
    async def build_snapshot(self, center_urns: list[str]) -> GraphSnapshot: ...