// Typed API wrapper for Cortex Autopilot backend

import {
  AssetNode,
  GraphSnapshot,
  ScenarioRequest,
  ScenarioResult,
  ImpactReport,
  Recommendation,
  ArtifactDraft,
  WritebackRecord,
} from "./types";
import { withAuth, clearAccessToken } from "./auth";
import type { CortexErrorResponse } from "./errorMapper";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** Custom error carrying the structured payload returned by the backend. */
export class CortexApiError extends Error {
  status: number;
  body: CortexErrorResponse | string | null;

  constructor(status: number, body: CortexErrorResponse | string | null, message?: string) {
    super(message ?? `API error: ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || "GET").toUpperCase();
  const headers: Record<string, string> = withAuth({
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> | undefined) ?? {},
  } as HeadersInit, method);
  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });
  if (res.status === 401) {
    clearAccessToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
    throw new CortexApiError(401, null, "Authentication required");
  }
  if (!res.ok) {
    let body: CortexErrorResponse | string | null = null;
    try {
      body = await res.json();
    } catch {
      try {
        body = await res.text();
      } catch {
        body = null;
      }
    }
    throw new CortexApiError(res.status, body);
  }
  return res.json();
}

export async function fetchAsset(urn: string): Promise<AssetNode> {
  const encoded = encodeURIComponent(urn);
  return request<AssetNode>(`${apiBase}/assets/${encoded}`);
}

export async function fetchLineage(urn: string): Promise<{ upstream: string[]; downstream: string[] }> {
  const encoded = encodeURIComponent(urn);
  return request(`${apiBase}/assets/${encoded}/lineage`);
}

export async function fetchGraph(urn: string): Promise<GraphSnapshot & { node_count: number; edge_count: number }> {
  const encoded = encodeURIComponent(urn);
  return request(`${apiBase}/assets/${encoded}/graph`);
}

export async function simulateScenario(payload: ScenarioRequest): Promise<ScenarioResult> {
  return request<ScenarioResult>(`${apiBase}/scenarios/simulate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function analyzeImpact(scenarioResult: ScenarioResult): Promise<ImpactReport> {
  return request<ImpactReport>(`${apiBase}/impact/analyze`, {
    method: "POST",
    body: JSON.stringify(scenarioResult),
  });
}

export async function generateRecommendation(
  impactReport: ImpactReport,
  scenarioType: string = "auto_detected"
): Promise<Recommendation> {
  const params = new URLSearchParams({ scenario_type: scenarioType });
  return request<Recommendation>(`${apiBase}/recommendations/generate?${params}`, {
    method: "POST",
    body: JSON.stringify(impactReport),
  });
}

export async function generateArtifact(
  recommendation: Recommendation,
  scenarioType: string = "auto_detected",
  assetName: string = "asset"
): Promise<ArtifactDraft> {
  const params = new URLSearchParams({ scenario_type: scenarioType, asset_name: assetName });
  return request<ArtifactDraft>(`${apiBase}/artifacts/generate?${params}`, {
    method: "POST",
    body: JSON.stringify(recommendation),
  });
}

export async function writebackResolution(
  assetUrn: string,
  impactReport: ImpactReport,
  recommendation: Recommendation,
  artifact?: ArtifactDraft
): Promise<WritebackRecord> {
  const body: any = {
    asset_urn: assetUrn,
    impact_report: impactReport,
    recommendation,
  };
  if (artifact) {
    body.artifact = artifact;
  }
  return request<WritebackRecord>(`${apiBase}/writeback`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface DemoResponse {
  asset: AssetNode;
  scenario: ScenarioResult;
  impact: ImpactReport;
  recommendation: Recommendation;
  artifact: ArtifactDraft;
  writeback: WritebackRecord;
}

export async function runDemo(payload: {
  asset_urn: string;
  scenario_type: string;
  change?: Record<string, any>;
  notes?: string;
}): Promise<DemoResponse> {
  return request<DemoResponse>(`${apiBase}/demo/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAssetResolutions(urn: string): Promise<WritebackRecord[]> {
  const encoded = encodeURIComponent(urn);
  return request<WritebackRecord[]>(`${apiBase}/writeback/assets/${encoded}/resolutions`);
}

export interface FutureSearchRequest {
  asset_urn: string;
  objective?: string;
  constraints?: Record<string, any>;
  policies?: Array<Record<string, any>>;
  connector?: string;
}

export async function runFutureSearch(payload: FutureSearchRequest): Promise<import("./types").FuturePlan> {
  return request<import("./types").FuturePlan>(`${apiBase}/future-search/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Policy endpoints ----------------------------------------------------------

export interface Policy {
  name: string;
  max_severity?: number;
  max_blast_radius?: number;
  require_owner?: boolean;
  action: "pass" | "warn" | "block";
}

export async function fetchPolicyDefaults(): Promise<{ policies: Policy[] }> {
  return request<{ policies: Policy[] }>(`${apiBase}/policy/defaults`);
}

export async function fetchPolicyExamples(): Promise<{ policies: Policy[] }> {
  return request<{ policies: Policy[] }>(`${apiBase}/policy/examples`);
}

export async function validatePolicies(payload: {
  policies: Policy[];
  severity: number;
  blast_radius: number;
  has_owner: boolean;
}): Promise<{ verdict: "pass" | "warn" | "block"; results: any[] }> {
  return request(`${apiBase}/policy/validate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// Health endpoints ----------------------------------------------------------

export async function fetchDetailedHealth(): Promise<any> {
  return request(`${apiBase}/health/detailed`);
}

export async function fetchHealth(): Promise<{ status: string; env: string }> {
  return request(`${apiBase}/health`);
}
