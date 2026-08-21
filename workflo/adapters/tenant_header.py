"""Header-based tenant resolver (default; matches the existing API client).

Sends an `X-Tenant-ID: <tenant>` header on every request. This is the scheme
the mock server understands, so it stays the default for zero-friction tests.
"""

from workflo.adapters.protocols import TenantAwareRequest


class HeaderTenantResolver:
    name = "header"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.header_name = cfg.get("header_name", "X-Tenant-ID")

    def configure(self, config: dict) -> None:
        self.header_name = config.get("header_name", self.header_name)

    def apply(self, request: TenantAwareRequest, tenant_id: str) -> None:
        request.headers[self.header_name] = tenant_id
