"""Tenant Shield adapters: pluggable tenant identity + auth.

Public registry API:

    from workflo.adapters import AdapterRegistry
    resolver, provider = AdapterRegistry.from_yaml("adapters.yaml")
"""

from workflo.adapters.auth_bearer import BearerAuthProvider
from workflo.adapters.auth_session import APIKeyAuthProvider, SessionAuthProvider
from workflo.adapters.protocols import AuthProvider, TenantAwareRequest, TenantResolver
from workflo.adapters.registry import AdapterRegistry, AUTH_PROVIDERS, RESOLVERS
from workflo.adapters.tenant_header import HeaderTenantResolver
from workflo.adapters.tenant_jwt import JWTTenantResolver
from workflo.adapters.tenant_subdomain import SubdomainTenantResolver

__all__ = [
    "AdapterRegistry",
    "AUTH_PROVIDERS",
    "RESOLVERS",
    "TenantResolver",
    "AuthProvider",
    "TenantAwareRequest",
    "HeaderTenantResolver",
    "SubdomainTenantResolver",
    "JWTTenantResolver",
    "BearerAuthProvider",
    "SessionAuthProvider",
    "APIKeyAuthProvider",
]
