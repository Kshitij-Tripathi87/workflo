import { RunStateSchema, type RunState } from "@workflo/contracts";
import type { TenantSession } from "../client";

/**
 * Class B — lifecycle resource.
 *
 * Runs are INSERTed in state CREATED. All state changes go through the
 * transition_run_state() SECURITY DEFINER function, which enforces the legal
 * transition graph and tenant ownership. The application role has no UPDATE
 * privilege on runs at all.
 */

export interface RunRow {
  id: string;
  organization_id: string;
  project_id: string;
  mission_id: string;
  created_by: string | null;
  state: RunState;
  sandbox_id: string | null;
  error: string | null;
  started_at: Date | null;
  finished_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export async function createRun(
  s: TenantSession,
  input: { projectId: string; missionId: string },
): Promise<RunRow> {
  const { rows } = await s.query<RunRow>(
    `INSERT INTO runs (organization_id, project_id, mission_id, created_by)
     VALUES ($1, $2, $3, $4) RETURNING *`,
    [s.ctx.orgId, input.projectId, input.missionId, s.ctx.userId ?? null],
  );
  return rows[0]!;
}

export async function getRun(s: TenantSession, id: string): Promise<RunRow | null> {
  const { rows } = await s.query<RunRow>(`SELECT * FROM runs WHERE id = $1`, [id]);
  return rows[0] ?? null;
}

export async function listRuns(s: TenantSession, missionId?: string): Promise<RunRow[]> {
  const { rows } = await s.query<RunRow>(
    missionId
      ? `SELECT * FROM runs WHERE mission_id = $1 ORDER BY created_at DESC`
      : `SELECT * FROM runs ORDER BY created_at DESC`,
    missionId ? [missionId] : undefined,
  );
  return rows;
}

/**
 * Transition a run through the validated state machine. Illegal transitions
 * and cross-tenant attempts raise inside the database.
 */
export async function transitionRun(
  s: TenantSession,
  runId: string,
  newState: RunState,
  meta?: { sandboxId?: string; error?: string },
): Promise<RunRow> {
  const state = RunStateSchema.parse(newState);
  const { rows } = await s.query<RunRow>(
    `SELECT * FROM transition_run_state($1, $2::run_state, $3::jsonb)`,
    [runId, state, JSON.stringify(meta ?? {})],
  );
  return rows[0]!;
}
