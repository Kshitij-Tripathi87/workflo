"""Result writeback — write test outcomes back to DataHub.

Maps Tenant Shield test outcomes → DataHub assertion events so the
next person or agent inherits knowledge about failures.

Modes:
  1. Assertion event: marks an assertion as PASS/FAIL on a dataset (default)
  2. Incident open: opens a DataHub incident when a critical test fails
  3. Documentation assertion: attaches a comment to the dataset page
"""

from typing import Optional
from workflo_datahub.client import DataHubClient
from workflo_utils.logging import get_logger

logger = get_logger(__name__)


class ResultWriteback:
    """Persists test results back to DataHub as assertions / incidents."""

    def __init__(self, client: DataHubClient):
        self.client = client

    def write_dataset_assertion(
        self,
        dataset_urn: str,
        assertion_urn: str,
        passed: bool,
        details: str = "",
    ) -> bool:
        """Record an assertion run outcome on the given dataset."""
        status = "passed" if passed else "failed"
        details = details or ("Auto-generated test passed" if passed else "Auto-generated test failed")
        ok = self.client.write_assertion(dataset_urn, assertion_urn, status, details)
        logger.info(
            "writeback.assertion",
            extra={"extra_data": {
                "dataset": dataset_urn, "assertion": assertion_urn,
                "status": status, "ok": ok,
            }},
        )
        return ok

    def open_incident_for_failure(
        self,
        dataset_urn: str,
        test_name: str,
        error: str,
    ) -> bool:
        """Open a DataHub incident when a critical test fails.

        Uses the GraphQL `createIncident` mutation if available; otherwise
        logs locally and returns False so callers can decide to alert.
        """
        # Best-effort: DataHub incident creation via REST
        url = f"{self.client.server_url}/api/v2/incident"
        payload = {
            "urn": dataset_urn,
            "incidentType": "FAILED_ASSERTION",
            "title": f"Test failure: {test_name}",
            "description": error,
        }
        try:
            import httpx
            with httpx.Client(headers=self.client._headers, timeout=15) as c:
                resp = c.post(url, json=payload)
                ok = resp.status_code in (200, 201, 202, 204)
                logger.info(
                    "writeback.incident",
                    extra={"extra_data": {"ok": ok, "status": resp.status_code, "test": test_name}},
                )
                return ok
        except Exception as exc:
            logger.warning("writeback.incident_failed", extra={"extra_data": {"error": str(exc)}})
            return False
