"""DataHub client — connects to DataHub via GraphQL (direct) or MCP Server.

Two connection modes:
  1. GraphQL (default): hits DataHub's `/api/graphql` endpoint directly.
     Used for reading datasets, schemas, lineage, and writing assertions back.
  2. MCP (optional): connects to a DataHub MCP server over stdio/HTTP.
     Useful when running inside an agent framework that requires MCP.

Both modes return the same Pydantic models so callers can swap transport freely.
"""

import json
import os
from typing import Optional
import httpx

from workflo_datahub.models import DatasetSchema, ColumnInfo, LineageEdge, DataHubEntity
from workflo_utils.logging import get_logger

logger = get_logger(__name__)

# GraphQL queries — tuned for DataHub's GMS GraphQL endpoint
SEARCH_DATASETS_QUERY = """
query searchDatasets($input: SearchInput!) {
  search(input: $input) {
    searchResults {
      entities {
        urn
        type
        ... on Dataset {
          name
          platform { name }
          schemaMetadata { name nativeDataType fields { fieldPath type type nullable description } }
          ownership { owners { owner { ... on CorpUser { username } ... on Group { name } } } }
        }
      }
    }
  }
}
"""

GET_DATASET_QUERY = """
query getDataset($urn: String!) {
  dataset(urn: $urn) {
    urn
    name
    platform { name }
    schemaMetadata {
      name
      nativeDataType
      fields { fieldPath type type nullable description primaryKey foreignKeys { foreignField { } } }
    }
    ownership { owners { owner { ... on CorpUser { username } ... on Group { name } } } }
    institutionalMemory { elements { url description } }
  }
}
"""

GET_LINEAGE_QUERY = """
query getLineage($urn: String!, $direction: LineageDirection!, $queryFinalEntities: [String!]) {
  dataset(urn: $urn) {
    lineage(direction: $direction, queryFinalEntities: $queryFinalEntities) {
      edges {
        source { urn name platform { name } }
        destination { urn name platform { name } }
        columnLineage { mappings { sourceField destinationField } }
      }
    }
  }
}
"""


class DataHubClient:
    """Async-capable DataHub client (GraphQL by default, MCP optional).

    Args:
        server_url: DataHub GMS base URL, e.g. 'http://localhost:8080'.
        token: Personal access token (optional, required if auth enabled).
        use_mcp: If True, route through an MCP server instance instead of GraphQL.
        mcp_command: Launch command for the MCP server subprocess (when use_mcp=True).
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        token: Optional[str] = None,
        use_mcp: bool = False,
        mcp_command: Optional[list[str]] = None,
    ):
        self.server_url = (server_url or os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")).rstrip("/")
        self.token = token or os.getenv("DATAHUB_TOKEN", "")
        self.use_mcp = use_mcp
        self.mcp_command = mcp_command
        self._mcp_session = None

    @property
    def _headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    # ---------- GraphQL backend ----------

    def _gql(self, query: str, variables: dict) -> dict:
        url = f"{self.server_url}/api/graphql"
        with httpx.Client(headers=self._headers, timeout=30) as c:
            resp = c.post(url, json={"query": query, "variables": variables})
            resp.raise_for_status()
            payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(f"DataHub GraphQL error: {payload['errors']}")
        return payload.get("data", {})

    # ---------- MCP backend (optional) ----------

    def _mcp_call(self, tool_name: str, arguments: dict) -> dict:
        """Call a DataHub MCP tool. Requires the `mcp` package installed."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import asyncio
        except ImportError as e:
            raise RuntimeError("MCP mode requires `pip install mcp`") from e

        async def _run():
            params = StdioServerParameters(command=self.mcp_command[0], args=self.mcp_command[1:] if len(self.mcp_command) > 1 else [])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return result
        return asyncio.run(_run())

    # ---------- Public API ----------

    def search_datasets(self, query: str = "*", limit: int = 50) -> list[DataHubEntity]:
        search_input = {"query": query, "start": 0, "count": limit, "entityType": "DATASET"}
        data = self._gql(SEARCH_DATASETS_QUERY, {"input": search_input}) if not self.use_mcp else self._mcp_resolve({
            "tool": "search_entities",
            "args": {"entity_type": "DATASET", "query": query, "limit": limit},
        })
        results = data.get("search", {}).get("searchResults", {}).get("entities", [])
        entities = []
        for e in results:
            entities.append(DataHubEntity(
                urn=e.get("urn", ""),
                type=e.get("type", "dataset"),
                name=e.get("name", ""),
                platform=e.get("platform", {}).get("name", "") if isinstance(e.get("platform"), dict) else "",
            ))
        return entities

    def get_dataset(self, urn: str) -> DatasetSchema:
        """Fetch a single dataset's full metadata (schema + ownership)."""
        if self.use_mcp:
            raw = self._mcp_resolve({"tool": "get_dataset", "args": {"urn": urn}})
        else:
            raw = self._gql(GET_DATASET_QUERY, {"urn": urn}).get("dataset", {})
        columns = []
        sm = raw.get("schemaMetadata") or {}
        for field in sm.get("fields", []):
            columns.append(ColumnInfo(
                name=field.get("fieldPath", field.get("path", "")),
                type=field.get("type", "UNKNOWN"),
                nullable=field.get("nullable", True),
                description=field.get("description", ""),
                primary_key=field.get("primaryKey", False),
            ))
        owner = ""
        ownership = raw.get("ownership") or {}
        owners = ownership.get("owners", [])
        if owners:
            owner_obj = owners[0].get("owner", {})
            owner = owner_obj.get("username", owner_obj.get("name", ""))
        return DatasetSchema(
            urn=raw.get("urn", urn),
            name=raw.get("name", ""),
            platform=raw.get("platform", {}).get("name", "") if isinstance(raw.get("platform"), dict) else "",
            columns=columns,
            owner=owner,
            description=str(raw.get("description") or ""),
        )

    def get_lineage(self, urn: str, direction: str = "UPSTREAM") -> list[LineageEdge]:
        """Fetch upstream/downstream lineage edges for a dataset."""
        if self.use_mcp:
            raw = self._mcp_resolve({
                "tool": "get_lineage",
                "args": {"urn": urn, "direction": direction},
            })
        else:
            raw = self._gql(GET_LINEAGE_QUERY, {"urn": urn, "direction": direction, "queryFinalEntities": None})
            raw = raw.get("dataset", {}).get("lineage", {})
        edges = []
        for e in raw.get("edges", []):
            src = e.get("source", {})
            dst = e.get("destination", {})
            mappings = []
            for m in (e.get("columnLineage") or {}).get("mappings", []):
                mappings.append({
                    "source": m.get("sourceField", ""),
                    "target": m.get("destinationField", ""),
                })
            edges.append(LineageEdge(
                source_urn=src.get("urn", ""),
                target_urn=dst.get("urn", ""),
                source_dataset=src.get("name", ""),
                target_dataset=dst.get("name", ""),
                column_mappings=mappings,
            ))
        return edges

    def write_assertion(self, dataset_urn: str, assertion_urn: str, status: str, details: str) -> bool:
        """Write a test result back to DataHub as an assertion run event.

        Uses DataHub's REST API `/api/v2/assertion/run` or GraphQL equivalent.
        Returns True if the writeback succeeded.
        """
        url = f"{self.server_url}/api/v2/assertion/run"
        payload = {
            "datasetUrn": dataset_urn,
            "assertionUrn": assertion_urn,
            "runId": status.upper(),
            "result": {
                "status": status,
                "type": "METRIC",
                "value": 1.0 if status == "passed" else 0.0,
            },
            "resultMeta": {"details": details},
        }
        try:
            with httpx.Client(headers=self._headers, timeout=15) as c:
                resp = c.post(url, json=payload)
                return resp.status_code in (200, 201, 202, 204)
        except Exception as exc:
            logger.warning("datahub.writeback_failed", extra={"extra_data": {"error": str(exc)}})
            return False

    # ---------- MCP helper ----------
    def _mcp_resolve(self, req: dict) -> dict:
        """Call a DataHub MCP tool and translate the result to GraphQL-shaped dict."""
        result = self._mcp_call(req["tool"], req["args"])
        if hasattr(result, "content") and result.content:
            return json.loads(result.content[0].text)
        return {}
