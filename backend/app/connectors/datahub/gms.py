"""Real DataHub GMS (Generalized Metadata Store) GraphQL/REST client.

This module provides an async client that talks to the DataHub GMS API
with retry, timeout, rate limiting, and structured error handling.
"""

import asyncio
import time
from typing import Any, Optional
from collections import deque

import httpx

from app.core.exceptions import (
    DataHubNotFoundError,
    DataHubAuthError,
    DataHubRateLimitedError,
    DataHubTimeoutError,
    DataHubConnectionError,
    DataHubError,
)
from app.models.asset import AssetNode
from app.core.settings import settings as _settings


class TokenBucketRateLimiter:
    """Simple token bucket rate limiter for outgoing requests."""

    def __init__(self, rate_per_second: float):
        self.rate = rate_per_second
        self.capacity = max(1, int(rate_per_second))
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1


class DataHubGMSClient:
    """Async client for DataHub GMS GraphQL and REST APIs."""

    GRAPHQL_PATH = "/api/graphql"
    REST_PATH = "/openapi/v2"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        rate_limit_rps: float | None = None,
    ):
        self.base_url = (base_url or _settings.DATAHUB_BASE_URL).rstrip("/") if (base_url or _settings.DATAHUB_BASE_URL) else ""
        self.token = token or _settings.DATAHUB_TOKEN
        self.timeout = timeout or _settings.DATAHUB_TIMEOUT
        self.max_retries = max_retries or _settings.DATAHUB_MAX_RETRIES
        self.rate_limiter = TokenBucketRateLimiter(
            rate_limit_rps or _settings.DATAHUB_RATE_LIMIT_RPS
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        operation: str = "unknown",
    ) -> dict:
        """Execute a request with retry, rate limiting, and error mapping."""
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            await self.rate_limiter.acquire()
            try:
                response = await client.request(
                    method, url, json=json, params=params
                )

                if response.status_code == 401:
                    raise DataHubAuthError(
                        "DataHub returned 401 - check token"
                    )
                if response.status_code == 404:
                    raise DataHubNotFoundError(url)
                if response.status_code == 429:
                    retry_after = int(
                        response.headers.get("Retry-After", "60")
                    )
                    if attempt < self.max_retries:
                        # Honor server-provided Retry-After (bounded by remaining attempts)
                        await asyncio.sleep(min(retry_after, 30))
                        continue
                    raise DataHubRateLimitedError(retry_after)

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException:
                last_error = DataHubTimeoutError(operation, self.timeout)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise last_error
            except httpx.ConnectError as e:
                last_error = DataHubConnectionError(
                    f"Cannot connect to DataHub at {self.base_url}: {e}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise last_error
            except (DataHubAuthError, DataHubNotFoundError) as e:
                # Non-retryable
                raise

        raise last_error or DataHubError("UNKNOWN", "Unknown DataHub error")

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query/mutation against DataHub."""
        payload = {"query": query, "variables": variables or {}}
        result = await self._request_with_retry(
            "POST",
            self.GRAPHQL_PATH,
            json=payload,
            operation="graphql",
        )
        if result.get("errors"):
            error = result["errors"][0]
            message = error.get("message", "GraphQL error")
            return {"_error": message, "_raw": result}
        return result.get("data", {})

    # --- Public API ---

    async def get_asset(self, urn: str) -> AssetNode:
        """Fetch an asset by URN and normalize to AssetNode."""
        query = """
        query getAsset($urn: String!) {
          entity(urn: $urn) {
            urn
            type
            ... on DataProcessInstance {
              name
            }
            ... on Dataset {
              name
              schemaMetadata(version: 0) {
                fields { fieldPath type }
              }
            }
          }
        }
        """
        data = await self._graphql(query, {"urn": urn})
        if not data.get("entity"):
            raise DataHubNotFoundError(urn)

        entity = data["entity"]
        return self._normalize_asset(entity)

    async def get_lineage(self, urn: str, direction: str = "DOWNSTREAM") -> dict:
        """Fetch upstream and downstream lineage."""
        query = """
        query getLineage($urn: String!, $direction: LineageDirection!, $count: Int!) {
          entity(urn: $urn) {
            lineage(direction: $direction, count: $count) {
              relationships {
                direction
                entity {
                  urn
                  type
                  name
                }
              }
            }
          }
        }
        """
        upstream = await self._graphql(
            query, {"urn": urn, "direction": "UPSTREAM", "count": 100}
        )
        downstream = await self._graphql(
            query, {"urn": urn, "direction": "DOWNSTREAM", "count": 100}
        )

        def extract(entity_data, dir_key):
            if not entity_data or not entity_data.get("entity"):
                return []
            rels = entity_data["entity"].get("lineage", {}).get("relationships", [])
            return [r["entity"]["urn"] for r in rels]

        return {
            "upstream": extract(upstream, "UPSTREAM"),
            "downstream": extract(downstream, "DOWNSTREAM"),
        }

    async def get_downstream(self, urn: str, limit: int = 100) -> list[str]:
        """Fetch downstream asset URNs."""
        lineage = await self.get_lineage(urn, direction="DOWNSTREAM")
        return lineage["downstream"][:limit]

    async def search_assets(
        self,
        query: str,
        types: list[str] | None = None,
        limit: int = 10,
    ) -> list[AssetNode]:
        """Search DataHub for assets."""
        gql = """
        query searchAssets($input: SearchInput!) {
          search(input: $input) {
            searchResults {
              entity {
                urn
                type
                name
              }
            }
          }
        }
        """
        variables = {
            "input": {
                "query": query,
                "start": 0,
                "count": limit,
                "entityTypes": types or ["DATASET", "DATA_JOB", "DASHBOARD", "ML_MODEL"],
            }
        }
        data = await self._graphql(gql, variables)
        results = data.get("search", {}).get("searchResults", [])
        return [
            self._normalize_asset({"urn": r["entity"]["urn"], "type": r["entity"]["type"], "name": r["entity"].get("name", "")})
            for r in results
        ]

    async def create_incident(self, payload: dict) -> str:
        """Create an incident on an asset. Returns the incident URN."""
        mutation = """
        mutation createIncident($input: CreateIncidentInput!) {
          createIncident(input: $input) {
            urn
          }
        }
        """
        variables = {
            "input": {
                "entityUrn": payload["urn"],
                "incidentType": payload.get("type", "SCHEMA_CHANGE_RISK"),
                "title": payload.get("title", "Cortex incident"),
                "description": payload.get("description", ""),
            }
        }
        data = await self._graphql(mutation, variables)
        return data.get("createIncident", {}).get("urn", "")

    async def add_tags(self, urn: str, tags: list[str]) -> None:
        """Add tags to an asset."""
        for tag in tags:
            mutation = """
            mutation addTag($input: TagAssociationInput!) {
              addTag(input: $input)
            }
            """
            variables = {
                "input": {
                    "entityUrn": urn,
                    "tag": tag,
                }
            }
            await self._graphql(mutation, variables)

    async def add_documentation(self, urn: str, markdown: str) -> None:
        """Attach markdown documentation to an asset."""
        mutation = """
        mutation updateDocumentation($urn: String!, $documentation: String!) {
          updateDatasetDocumentation(urn: $urn, documentation: $documentation)
        }
        """
        await self._graphql(mutation, {"urn": urn, "documentation": markdown})

    # --- Normalization helpers ---

    @staticmethod
    def _normalize_asset(entity: dict) -> AssetNode:
        """Convert a raw DataHub entity dict to an AssetNode."""
        kind_map = {
            "DATASET": "dataset",
            "DATA_JOB": "pipeline",
            "DASHBOARD": "dashboard",
            "ML_MODEL": "model",
        }
        kind = kind_map.get(entity.get("type", ""), "dataset")

        schema_fields = []
        schema = entity.get("schemaMetadata") or entity.get("schema")
        if schema and isinstance(schema, dict):
            for f in schema.get("fields", []):
                schema_fields.append(f.get("fieldPath", "") or f.get("fieldName", ""))

        return AssetNode(
            urn=entity.get("urn", ""),
            name=entity.get("name", ""),
            kind=kind,
            schema_fields=schema_fields,
        )
