/**
 * ErrorMapper — translates backend error codes into user-facing toast payloads.
 *
 * The backend returns structured errors with `code`, `message`, `details`,
 * and `hint` fields. This mapper turns them into friendly notifications
 * with sensible defaults so the UI never has to special-case each one.
 */

import type { ToastKind, ToastPayload } from "../components/Toast";

export interface CortexErrorResponse {
  error?: string;
  message?: string;
  details?: Record<string, unknown>;
  hint?: string;
}

const SEVERITY_MAP: Record<string, ToastKind> = {
  VALIDATION_ERROR: "warn",
  NOT_FOUND: "warn",
  AUTH_ERROR: "warn",
  FORBIDDEN: "warn",
  CONNECTOR_MANIFEST_MISSING: "error",
  CONNECTOR_NOT_CONFIGURED: "warn",
  CONNECTOR_CONNECTION_FAILED: "error",
  SNAPSHOT_TIMEOUT: "error",
  SNAPSHOT_EMPTY: "warn",
  POLICY_VIOLATION: "warn",
  POLICY_INVALID_CONFIG: "error",
  DATAHUB_NOT_FOUND: "warn",
  DATAHUB_AUTH_ERROR: "error",
  DATAHUB_RATE_LIMITED: "warn",
  DATAHUB_TIMEOUT: "warn",
  DATAHUB_CONNECTION_ERROR: "error",
  INTERNAL_ERROR: "error",
};

const TITLES: Record<string, string> = {
  VALIDATION_ERROR: "Check your input",
  NOT_FOUND: "Not found",
  AUTH_ERROR: "Authentication required",
  FORBIDDEN: "Access denied",
  CONNECTOR_MANIFEST_MISSING: "dbt manifest not found",
  CONNECTOR_NOT_CONFIGURED: "Connector not configured",
  CONNECTOR_CONNECTION_FAILED: "Connection failed",
  SNAPSHOT_TIMEOUT: "Graph traversal timed out",
  SNAPSHOT_EMPTY: "Empty graph snapshot",
  POLICY_VIOLATION: "Policy violation",
  POLICY_INVALID_CONFIG: "Invalid policy",
  DATAHUB_NOT_FOUND: "DataHub asset not found",
  DATAHUB_AUTH_ERROR: "DataHub authentication failed",
  DATAHUB_RATE_LIMITED: "Rate limited",
  DATAHUB_TIMEOUT: "DataHub timed out",
  DATAHUB_CONNECTION_ERROR: "DataHub unreachable",
  INTERNAL_ERROR: "Something went wrong",
};

export function mapErrorToToast(
  status: number,
  body: CortexErrorResponse | string | null | undefined,
): ToastPayload {
  if (typeof body === "string" || body == null) {
    return {
      kind: status >= 500 ? "error" : "warn",
      title: status >= 500 ? "Server error" : "Request failed",
      message:
        (typeof body === "string" ? body : null) ||
        `The server returned status ${status}.`,
    };
  }

  const code = body.error || "UNKNOWN_ERROR";
  const kind: ToastKind = SEVERITY_MAP[code] || (status >= 500 ? "error" : "warn");
  const title = TITLES[code] || prettifyCode(code);
  return {
    kind,
    title,
    message: body.message || `The server returned error code ${code}.`,
    hint: body.hint,
  };
}

function prettifyCode(code: string): string {
  return code
    .toLowerCase()
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}
