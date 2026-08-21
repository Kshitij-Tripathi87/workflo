"""Subdomain-based tenant resolver.

Supports schemes like `https://company1.app.workflowpro.com` and
`https://workflowpro.com/company1/...`. Two modes:

  - mode `subdomain`: rewrites `request.base_url` so the hostname's first label
    is replaced with the target tenant. e.g. base `https://app.example.com`
    request for tenant `acme` becomes `https://acme.example.com`.
  - mode `prefix`: prepends `/<tenant>` to the request path.
"""

from urllib.parse import urlsplit, urlunsplit

from workflo.adapters.protocols import TenantAwareRequest


class SubdomainTenantResolver:
    name = "subdomain"

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.mode = cfg.get("mode", "subdomain")
        self.base_host = cfg.get("base_host")  # e.g. "app.workflowpro.com"

    def configure(self, config: dict) -> None:
        self.mode = config.get("mode", self.mode)
        self.base_host = config.get("base_host", self.base_host)

    def apply(self, request: TenantAwareRequest, tenant_id: str) -> None:
        if self.mode == "prefix":
            request.path = f"/{tenant_id}{request.path}"
            return

        # subdomain mode: rewrite the base_url hostname.
        parts = urlsplit(request.base_url)
        host = self.base_host or parts.hostname or ""
        if not host:
            return
        scheme = parts.scheme or "https"
        new_host = f"{tenant_id}.{host}"
        netloc = new_host
        if parts.port:
            netloc = f"{new_host}:{parts.port}"
        request.base_url = urlunsplit((scheme, netloc, "", "", ""))
