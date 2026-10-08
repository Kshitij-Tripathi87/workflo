"""Structured error types for the Cortex Autopilot application.

Every error includes:
  - code: machine-readable error code (e.g. "CONNECTOR_MANIFEST_MISSING")
  - message: human-readable description
  - details: structured context
  - hint: actionable next step for the user

The frontend `ErrorMapper` turns these codes into toast notifications,
while the backend surfaces them in JSON responses.
"""


class CortexError(Exception):
    """Base error for all application errors."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.hint = hint
        super().__init__(message)

    @property
    def status_code(self) -> int:
        return 500

    def to_dict(self) -> dict:
        payload = {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.hint:
            payload["hint"] = self.hint
        return payload


class CortexValidationError(CortexError):
    """Client provided invalid input."""

    def __init__(
        self,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__("VALIDATION_ERROR", message, details, hint)

    @property
    def status_code(self) -> int:
        return 400


class CortexNotFoundError(CortexError):
    """Requested resource does not exist."""

    def __init__(self, resource: str, identifier: str, hint: str | None = None):
        super().__init__(
            "NOT_FOUND",
            f"{resource} not found: {identifier}",
            {"resource": resource, "identifier": identifier},
            hint,
        )

    @property
    def status_code(self) -> int:
        return 404


class CortexAuthError(CortexError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__("AUTH_ERROR", message)

    @property
    def status_code(self) -> int:
        return 401


class CortexForbiddenError(CortexError):
    """User lacks permission."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__("FORBIDDEN", message)

    @property
    def status_code(self) -> int:
        return 403


class CortexInternalError(CortexError):
    """Internal server error."""

    def __init__(
        self,
        message: str = "Internal server error",
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__("INTERNAL_ERROR", message, details, hint)


# ---------- Connector errors ----------
class ConnectorError(CortexError):
    """Base error for any connector (dbt, Snowflake, DataHub, ...)."""

    def __init__(
        self,
        connector: str,
        code: str,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__(f"CONNECTOR_{code}", message, details, hint)
        self.connector = connector


class ConnectorManifestMissingError(ConnectorError, FileNotFoundError):
    """dbt manifest.json not found."""

    def __init__(self, manifest_path: str):
        super().__init__(
            connector="dbt",
            code="MANIFEST_MISSING",
            message=f"dbt manifest not found at {manifest_path}",
            details={"manifest_path": manifest_path},
            hint=(
                "Run `dbt compile` or `dbt docs generate` in your dbt project "
                "to produce target/manifest.json, or set CORTEX_DBT_MANIFEST_PATH "
                "to the correct location."
            ),
        )


class ConnectorNotConfiguredError(ConnectorError):
    """Required configuration for the connector is missing."""

    def __init__(self, connector: str, missing: list[str]):
        super().__init__(
            connector=connector,
            code="NOT_CONFIGURED",
            message=f"{connector} connector is missing required configuration: {', '.join(missing)}",
            details={"missing_fields": missing},
            hint=f"Set the {', '.join(missing)} environment variable(s) or disable the {connector} connector.",
        )


class ConnectorConnectionError(ConnectorError):
    """Connector cannot reach its data source."""

    def __init__(self, connector: str, target: str, reason: str | None = None):
        super().__init__(
            connector=connector,
            code="CONNECTION_FAILED",
            message=f"{connector} could not connect to {target}"
            + (f": {reason}" if reason else ""),
            details={"target": target, "reason": reason},
            hint=f"Check that {target} is reachable and that credentials are valid.",
        )


# ---------- Snapshot errors ----------
class SnapshotError(CortexError):
    """Errors building or traversing the asset graph snapshot."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__(f"SNAPSHOT_{code}", message, details, hint)


class SnapshotTimeoutError(SnapshotError):
    """Graph traversal exceeded its time budget."""

    def __init__(self, start_urn: str, depth: int, budget_seconds: float):
        super().__init__(
            code="TIMEOUT",
            message=f"Graph traversal from {start_urn} exceeded {budget_seconds}s at depth {depth}",
            details={
                "start_urn": start_urn,
                "depth": depth,
                "budget_seconds": budget_seconds,
            },
            hint=(
                "The asset graph may have a cycle or unusually deep downstream chain. "
                "Try reducing the blast-radius search depth or check for misconfigured parents."
            ),
        )


class SnapshotEmptyError(SnapshotError):
    """No assets were loaded into the snapshot."""

    def __init__(self, source: str):
        super().__init__(
            code="EMPTY",
            message=f"Graph snapshot from {source} contains no assets",
            details={"source": source},
            hint="Verify that the manifest/catalog files contain nodes and that paths are correct.",
        )


# ---------- Policy errors ----------
class PolicyError(CortexError):
    """Base error for policy evaluation issues."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__(f"POLICY_{code}", message, details, hint)


class PolicyViolationError(PolicyError):
    """A change was rejected by a named policy."""

    def __init__(
        self,
        policy_name: str,
        verdict: str,
        reason: str,
        trigger_values: dict | None = None,
    ):
        super().__init__(
            code="VIOLATION",
            message=f"Policy '{policy_name}' verdict={verdict}: {reason}",
            details={
                "policy_name": policy_name,
                "verdict": verdict,
                "reason": reason,
                "trigger_values": trigger_values or {},
            },
            hint=(
                "Adjust your policies in cortex.yml, or mitigate the impact (e.g., add a "
                "compatibility view) and re-run the gate."
            ),
        )


class PolicyConfigError(PolicyError):
    """Policy definition is malformed."""

    def __init__(self, reason: str, raw: dict | None = None):
        super().__init__(
            code="INVALID_CONFIG",
            message=f"Invalid policy configuration: {reason}",
            details={"raw": raw or {}},
            hint="See docs/policy.md for the supported policy fields.",
        )


# ---------- DataHub-specific errors ----------
class DataHubError(CortexError):
    """Base error for DataHub API failures."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__(f"DATAHUB_{code}", message, details, hint)


class DataHubNotFoundError(DataHubError):
    def __init__(self, urn: str):
        super().__init__(
            "NOT_FOUND",
            f"DataHub asset not found: {urn}",
            {"urn": urn},
            hint="Confirm the URN matches an existing dataset in DataHub.",
        )

    @property
    def status_code(self) -> int:
        return 404


class DataHubAuthError(DataHubError):
    def __init__(self, message: str = "DataHub authentication failed"):
        super().__init__(
            "AUTH_ERROR",
            message,
            hint="Check DATAHUB_TOKEN is a valid Personal Access Token.",
        )

    @property
    def status_code(self) -> int:
        return 401


class DataHubRateLimitedError(DataHubError):
    def __init__(self, retry_after: int | None = None):
        super().__init__(
            "RATE_LIMITED",
            "DataHub rate limit exceeded",
            {"retry_after": retry_after},
            hint="Slow down or upgrade your DataHub tier.",
        )

    @property
    def status_code(self) -> int:
        return 429


class DataHubTimeoutError(DataHubError):
    def __init__(self, operation: str, timeout: int):
        super().__init__(
            "TIMEOUT",
            f"DataHub operation timed out after {timeout}s: {operation}",
            {"operation": operation, "timeout": timeout},
            hint="Increase the timeout via DATAHUB_TIMEOUT_SECONDS or check DataHub GMS health.",
        )


class DataHubConnectionError(DataHubError):
    def __init__(
        self,
        message: str,
        details: dict | None = None,
        hint: str | None = None,
    ):
        super().__init__("CONNECTION_ERROR", message, details, hint)
