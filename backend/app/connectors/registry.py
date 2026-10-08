"""String-keyed factory for connector lookups.

Each connector module calls `register("name", ConnectorClass)` at import
time. The API layer calls `get_connector("name")` to obtain a fresh
instance — no conditionals, no if/else chains.

This is intentionally minimal: a dict. We resist building an
"ConnectorRegistry framework" until we have 3+ connectors that share
non-trivial logic (the rule of three).
"""
from typing import Type

from app.connectors.base import BaseConnector


_REGISTRY: dict[str, Type[BaseConnector]] = {}


def register(name: str, cls: Type[BaseConnector]) -> None:
    """Register a connector class under a string name.

    Idempotent: re-registering the same name replaces the previous class.
    Called at module import time by each connector package.
    """
    _REGISTRY[name] = cls


def get_connector(name: str) -> BaseConnector:
    """Instantiate a connector by name.

    Raises ValueError with the list of available names if `name` is unknown.
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown connector: {name!r}. Available: {list(_REGISTRY)}"
        )
    return cls()


def list_connectors() -> list[str]:
    """Return all registered connector names (for /health, /version, etc.)."""
    return sorted(_REGISTRY)


def is_registered(name: str) -> bool:
    return name in _REGISTRY
