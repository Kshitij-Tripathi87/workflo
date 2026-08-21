"""Registry mapping config keys to adapter classes.

Reads `adapters.yaml` (or a dict) and returns instantiated
`TenantResolver` + `AuthProvider` ready to plug into the API client:

    resolver, provider = AdapterRegistry.from_yaml("adapters.yaml")
"""

import os
from typing import Optional, Tuple

import yaml

from workflo.adapters.auth_bearer import BearerAuthProvider
from workflo.adapters.auth_session import APIKeyAuthProvider, SessionAuthProvider
from workflo.adapters.protocols import AuthProvider, TenantResolver
from workflo.adapters.tenant_header import HeaderTenantResolver
from workflo.adapters.tenant_jwt import JWTTenantResolver
from workflo.adapters.tenant_subdomain import SubdomainTenantResolver


RESOLVERS = {
    "header": HeaderTenantResolver,
    "subdomain": SubdomainTenantResolver,
    "jwt": JWTTenantResolver,
}

AUTH_PROVIDERS = {
    "bearer": BearerAuthProvider,
    "session": SessionAuthProvider,
    "api_key": APIKeyAuthProvider,
}


class AdapterRegistry:
    """Maps adapter names to instances and resolves them from config."""

    def __init__(self, resolvers=None, auth_providers=None):
        self.resolvers = dict(resolvers or RESOLVERS)
        self.auth_providers = dict(auth_providers or AUTH_PROVIDERS)

    def register_resolver(self, name: str, cls):
        self.resolvers[name] = cls

    def register_auth_provider(self, name: str, cls):
        self.auth_providers[name] = cls

    def build_resolver(self, config: dict) -> TenantResolver:
        name = config.get("tenant_resolver", "header")
        sub = config.get("tenant_resolver_config") or {}
        cls = self.resolvers.get(name)
        if cls is None:
            raise ValueError(f"Unknown tenant_resolver: {name!r} (known: {sorted(self.resolvers)})")
        return cls(sub)

    def build_auth_provider(self, config: dict) -> AuthProvider:
        name = config.get("auth_provider", "bearer")
        sub = config.get("auth_provider_config") or {}
        cls = self.auth_providers.get(name)
        if cls is None:
            raise ValueError(f"Unknown auth_provider: {name!r} (known: {sorted(self.auth_providers)})")
        return cls(sub)

    def build(self, config: dict) -> Tuple[TenantResolver, AuthProvider]:
        return self.build_resolver(config), self.build_auth_provider(config)

    @classmethod
    def from_yaml(cls, path: str, registry: Optional["AdapterRegistry"] = None) -> Tuple[TenantResolver, AuthProvider]:
        if not os.path.exists(path):
            # Fall back to defaults so users with no adapters.yaml still work.
            return HeaderTenantResolver(), BearerAuthProvider()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return (registry or cls()).build(data)


__all__ = [
    "AdapterRegistry",
    "RESOLVERS",
    "AUTH_PROVIDERS",
    "TenantResolver",
    "AuthProvider",
]
