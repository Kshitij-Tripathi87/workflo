import type { TenantSession } from "../client";

/**
 * Class C — append-only inference telemetry. Measurements only; billing logic
 * lives elsewhere.
 */

export interface InferenceUsageRow {
  id: string;
  organization_id: string;
  project_id: string;
  run_id: string;
  model_id: string;
  model_version: string | null;
  request_id: string;
  input_tokens: number;
  output_tokens: number;
  inference_seconds: string;
  queue_seconds: string;
  created_at: Date;
}

export async function recordInferenceUsage(
  s: TenantSession,
  input: {
    projectId: string;
    runId: string;
    modelId: string;
    requestId: string;
    inputTokens: number;
    outputTokens: number;
    inferenceSeconds: number;
    modelVersion?: string;
    queueSeconds?: number;
  },
): Promise<InferenceUsageRow> {
  const { rows } = await s.query<InferenceUsageRow>(
    `INSERT INTO inference_usage
      (organization_id, project_id, run_id, model_id, model_version,
       request_id, input_tokens, output_tokens, inference_seconds, queue_seconds)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
     RETURNING *`,
    [
      s.ctx.orgId,
      input.projectId,
      input.runId,
      input.modelId,
      input.modelVersion ?? null,
      input.requestId,
      input.inputTokens,
      input.outputTokens,
      input.inferenceSeconds,
      input.queueSeconds ?? 0,
    ],
  );
  return rows[0]!;
}

export async function listRunUsage(
  s: TenantSession,
  runId: string,
): Promise<InferenceUsageRow[]> {
  const { rows } = await s.query<InferenceUsageRow>(
    `SELECT * FROM inference_usage WHERE run_id = $1 ORDER BY created_at`,
    [runId],
  );
  return rows;
}
