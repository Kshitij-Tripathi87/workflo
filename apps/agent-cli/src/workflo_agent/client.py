"""API client for communicating with the Tenant Shield Control Plane."""

import httpx
from typing import Optional
from workflo_utils.config import get_config_value


class ControlPlaneClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or get_config_value("auth.api_key")
        self.base_url = base_url or get_config_value("defaults.api_base_url", "https://api.tenantshield.dev")

    @property
    def headers(self) -> dict:
        return {"X-TenantShield-Key": self.api_key or ""}

    def submit_run(self, spec: dict) -> dict:
        with httpx.Client(headers=self.headers, timeout=30) as client:
            resp = client.post(f"{self.base_url}/v1/runs", json=spec)
            resp.raise_for_status()
            return resp.json()

    def get_run(self, run_id: str) -> dict:
        with httpx.Client(headers=self.headers, timeout=30) as client:
            resp = client.get(f"{self.base_url}/v1/runs/{run_id}")
            resp.raise_for_status()
            return resp.json()

    def list_runs(self, limit: int = 20) -> list:
        with httpx.Client(headers=self.headers, timeout=30) as client:
            resp = client.get(f"{self.base_url}/v1/runs", params={"limit": limit})
            resp.raise_for_status()
            return resp.json()

    async def stream_run_logs(self, run_id: str) -> None:
        async with httpx.AsyncClient(headers=self.headers, timeout=None) as client:
            async with client.stream("GET", f"{self.base_url}/v1/runs/{run_id}/logs") as resp:
                async for line in resp.aiter_lines():
                    print(line)
