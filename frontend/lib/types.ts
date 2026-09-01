// Backend models mirrored in TypeScript

export type Severity = "low" | "medium" | "high" | "critical";
export type AssetKind = "dataset" | "pipeline" | "dashboard" | "model" | "feature";
export type ArtifactType = "sql" | "dbt" | "dag" | "yaml" | "markdown";
export type WritebackStatus = "open" | "triaged" | "mitigated" | "fixed" | "dismissed";
export type RecommendationAction =
  | "patch_sql"
  | "patch_dbt"
  | "patch_dag"
  | "assign_owner"
  | "create_temp_view"
  | "rollback_change"
  | "archive_asset"
  | "escalate";

export interface AssetNode {
  urn: string;
  name: string;
  kind: AssetKind;
  owner: string | null;
  description: string | null;
  schema_fields: string[];
  upstream: string[];
  downstream: string[];
  tags: string[];
  freshness: string | null;
  criticality: Severity;
  status: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: string;
  confidence: number;
}

export interface GraphSnapshot {
  nodes: Record<string, AssetNode>;
  edges: GraphEdge[];
}

export interface ScenarioRequest {
  asset_urn: string;
  scenario_type: string;
  change: Record<string, any>;
  notes?: string | null;
}

export interface ScenarioResult {
  scenario_id: string;
  asset_urn: string;
  scenario_type: string;
  applied_change: Record<string, any>;
  predicted_breakages: string[];
  predicted_severity: Severity;
  confidence: number;
}

export interface ImpactReport {
  impact_id: string;
  asset_urn: string;
  affected_assets: string[];
  affected_dashboards: string[];
  affected_models: string[];
  affected_pipelines: string[];
  severity: Severity;
  reason: string;
  confidence: number;
  explanation: string[];
}

export interface Recommendation {
  recommendation_id: string;
  impact_id: string;
  action_type: RecommendationAction;
  title: string;
  rationale: string;
  confidence: number;
  risk: Severity;
  artifacts: string[];
  fallback_action?: RecommendationAction | null;
}

export interface ArtifactDraft {
  artifact_id: string;
  recommendation_id: string;
  artifact_type: ArtifactType;
  title: string;
  body: string;
  file_path: string | null;
  confidence: number;
}

export interface WritebackRecord {
  record_id: string;
  asset_urn: string;
  status: WritebackStatus;
  summary: string;
  linked_artifact: string | null;
  affected_assets: string[];
  created_by: string;
  created_at: string;
}

export interface FutureScenario {
  future_id: string;
  asset_urn: string;
  scenario_type: string;
  change: Record<string, any>;
  predicted_severity: number;
  predicted_effort: number;
  predicted_benefit: number;
  confidence: number;
  evidence: string[];
}

export interface FuturePlan {
  plan_id: string;
  asset_urn: string;
  objective: string;
  candidates: FutureScenario[];
  ranked_choice: FutureScenario;
  rationale: string;
  explanation: string[];
  created_at: string;
  receipt?: SignedReceipt;
}

export interface GeneratedContractTest {
  test_id: string;
  dataset_urn: string;
  dataset_name: string;
  test_code: string;
  test_type: string;
  soc2_controls: string[];
  integrity_score: number;
  created_at: string;
}

export interface ContractExecutionResult {
  dataset_urn: string;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  duration_seconds: number;
  status: "passed" | "failed" | "warning";
  findings: Array<{ test: string; status: string; detail: string }>;
  receipt_id?: string;
  soc2_compliance_met: boolean;
}

export interface TeardownProof {
  sandbox_id: string;
  filesystem_wipe_method: string;
  container_removed: boolean;
  filesystem_removed: boolean;
  no_snapshot_retained: boolean;
  destroyed_at: string;
  session_duration_seconds: number;
  peak_memory_mb: number;
}

export interface SignedReceipt {
  receipt_id: string;
  action_type: string;
  asset_urn: string;
  timestamp: string;
  parameters_hash: string;
  result_summary: Record<string, any>;
  soc2_controls: string[];
  teardown_proof?: TeardownProof;
  public_key_fingerprint?: string;
  signature?: string;
}

export interface ReceiptVerificationResponse {
  receipt_id: string;
  is_valid: boolean;
  signer_fingerprint: string;
  verified_at: string;
  tamper_detected: boolean;
  message: string;
}

export interface SOC2ControlStatus {
  control_id: string;
  name: string;
  description: string;
  status: "compliant" | "warning" | "non_compliant";
  score: number;
  audited_assets_count: number;
  violating_assets: string[];
  recommendations: string[];
}

export interface ComplianceReport {
  report_id: string;
  generated_at: string;
  overall_compliance_score: number;
  status: "passing" | "needs_review" | "failing";
  controls: Record<string, SOC2ControlStatus>;
  total_assets: number;
  unowned_critical_assets: string[];
  schema_drift_count: number;
  cryptographic_receipt_coverage_pct: number;
}