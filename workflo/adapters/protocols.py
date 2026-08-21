"""Adapter protocols for tenant identity resolution and authentication.

Real-world B2B SaaS apps express tenant identity in many ways: a request
header, a URL subdomain, a JWT claim, a path prefix, etc. Authentication is
similarly varied (bearer token, API key, session cookie, mTLS).

Tenant Shield uses two small protocols so the same isolation library can drive
tests against any customer stack without changing the test code:

  - `TenantResolver`: given a target tenant + base config, returns the headers
    (and optional path transform) that carry tenant identity on the wire.
  - `AuthProvider`: given a credential handle, returns the auth headers to
    attach to the request.

Implementations live in sibling modules; `registry.py` maps config keys to
implementations.
"""

from typing import Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class TenantResolver(Protocol):
    """Translates a tenant identity into HTTP request modifications."""

    name: str

    def configure(self, config: dict) -> None: ...

    def apply(self, request: "TenantAwareRequest", tenant_id: str) -> None:
        """Attach tenant identity to the outgoing request (headers and/or URL)."""
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Translates credentials into HTTP Authorization headers."""

    name: str

    def configure(self, config: dict) -> None: ...

    def auth_headers(self, credentials: str) -> Dict[str, str]: ...


class TenantAwareRequest:
    """Lightweight carrier for the request shape the adapter can modify.

    The API client builds this from a method/path/kwargs tuple, lets adapters
    mutate headers + the URL, then issues the request. Keeping it minimal and
    decoupled from `requests.Request` means adapters are unit-testable without
    network I/O.
    """

    def __init__(self, base_url: str, path: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url
        self.path = path
        self.headers: Dict[str, str] = dict(headers or {})

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"
