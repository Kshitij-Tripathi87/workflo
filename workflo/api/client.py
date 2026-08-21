import os

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import ConnectionError, Timeout, HTTPError

from workflo.adapters import (
    AdapterRegistry,
    BearerAuthProvider,
    HeaderTenantResolver,
    TenantAwareRequest,
)


class APIClient:
    """HTTP client carrying tenant identity and auth on every request.

    Default behavior matches the previous hardcoded implementation: an
    `X-Tenant-ID` header + `Authorization: Bearer <token>`. To target a
    different scheme (subdomain-based tenant, JWT-claim tenant, API key auth,
    session cookie auth, etc.), pass `tenant_resolver=` and/or
    `auth_provider=` built from `AdapterRegistry`, or `adapters_config=` to
    load from a dict.
    """

    def __init__(
        self,
        base_url=None,
        tenant_id=None,
        auth_token=None,
        *,
        tenant_resolver=None,
        auth_provider=None,
        adapters_config=None,
        adapters_yaml=None,
    ):
        self.base_url = base_url or os.getenv("API_BASE_URL", "https://api.workflowpro.com")
        self.tenant_id = tenant_id or os.getenv("TENANT_ID", "company1")

        if adapters_config or adapters_yaml:
            reg = AdapterRegistry()
            resolver, provider = (
                reg.build(adapters_config) if adapters_config
                else AdapterRegistry.from_yaml(adapters_yaml, reg)
            )
            tenant_resolver = tenant_resolver or resolver
            auth_provider = auth_provider or provider

        self.tenant_resolver = tenant_resolver or HeaderTenantResolver()
        self.auth_provider = auth_provider or BearerAuthProvider()

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._auth_token = auth_token
        if auth_token:
            self.session.headers.update(self.auth_provider.auth_headers(auth_token))

    def set_auth_token(self, token):
        self._auth_token = token
        for h in list(self.session.headers.keys()):
            if h.lower() in ("authorization", "x-api-key", "cookie"):
                del self.session.headers[h]
        self.session.headers.update(self.auth_provider.auth_headers(token))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, Timeout, HTTPError)),
        reraise=True,
    )
    def request(self, method, path, **kwargs):
        request = TenantAwareRequest(self.base_url, path, dict(self.session.headers))
        self.tenant_resolver.apply(request, self.tenant_id)
        if self._auth_token and not _has_auth_header(request.headers):
            request.headers.update(self.auth_provider.auth_headers(self._auth_token))

        url = request.url
        headers = request.headers
        response = self.session.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 500:
            response.raise_for_status()
        return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


def _has_auth_header(headers):
    return any(k.lower() in ("authorization", "x-api-key", "cookie") for k in headers)
