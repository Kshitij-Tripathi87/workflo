import { JudgeVerdictSchema, type JudgeVerdict } from "@workflo/contracts";
import type { TenantSession } from "../client";

/**
 * Class B (hybrid) — findings.
 *
 * A finding begins as an Explorer hypothesis (PROPOSED). Only the
 * judge_finding() function may set the verdict (CONFIRMED / UNCONFIRMED /
 * INSUFFICIENT_CONTROL / ERROR) and freeze the record. Verdicts reference
 * ledger evidence; the database enforces that reference.
 */

export type FindingStatus = "PROPOSED" | JudgeVerdict;
export type FindingSeverity = "info" | "low" | "medium" | "high" | "critical";

export interface FindingRow {
  id: string;
  organization_id: string;
  project_id: string;
  run_id: string;
  title: string;
  summary: string;
  severity: FindingSeverity;
  status: FindingStatus;
  confidence: "low" | "medium" | "high" | null;
  evidence_refs: string[];
  decided_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export async function proposeFinding(
  s: TenantSession,
  input: {
    projectId: string;
    runId: string;
    title: string;
    summary?: string;
    severity?: FindingSeverity;
  },
): Promise<FindingRow> {
  const { rows } = await s.query<FindingRow>(
    `INSERT INTO findings (organization_id, project_id, run_id, title, summary, severity)
     VALUES ($1, $2, $3, $4, $5, $6)
     RETURNING *`,
    [
      s.ctx.orgId,
      input.projectId,
      input.runId,
      input.title,
      input.summary ?? "",
      input.severity ?? "info",
    ],
  );
  return rows[0]!;
}

/** Judge a finding. The function validates tenancy + evidence refs. */
export async function judgeFinding(
  s: TenantSession,
  findingId: string,
  verdict: JudgeVerdict,
  confidence: "low" | "medium" | "high" | null,
  evidenceRefs: string[],
): Promise<FindingRow> {
  const parsedVerdict = JudgeVerdictSchema.parse(verdict);
  const { rows } = await s.query<FindingRow>(
    `SELECT * FROM judge_finding($1, $2::finding_status, $3::judge_confidence, $4::uuid[])`,
    [findingId, parsedVerdict, confidence, evidenceRefs],
  );
  return rows[0]!;
}

export async function getFinding(s: TenantSession, id: string): Promise<FindingRow | null> {
  const { rows } = await s.query<FindingRow>(
    `SELECT * FROM findings WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function listRunFindings(s: TenantSession, runId: string): Promise<FindingRow[]> {
  const { rows } = await s.query<FindingRow>(
    `SELECT * FROM findings WHERE run_id = $1 ORDER BY created_at`,
    [runId],
  );
  return rows;
}
