import type { TenantSession } from "../client";

/**
 * Class A — mission definition (what should be verified).
 */

export interface Mission {
  id: string;
  organization_id: string;
  project_id: string;
  created_by: string | null;
  title: string;
  intent: string;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  config: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
}

export async function createMission(
  s: TenantSession,
  input: { projectId: string; title: string; intent: string; config?: Record<string, unknown> },
): Promise<Mission> {
  const { rows } = await s.query<Mission>(
    `INSERT INTO missions (organization_id, project_id, created_by, title, intent, config)
     VALUES ($1, $2, $3, $4, $5, COALESCE($6::jsonb, '{}'::jsonb))
     RETURNING *`,
    [
      s.ctx.orgId,
      input.projectId,
      s.ctx.userId ?? null,
      input.title,
      input.intent,
      input.config ? JSON.stringify(input.config) : null,
    ],
  );
  return rows[0]!;
}

export async function getMission(s: TenantSession, id: string): Promise<Mission | null> {
  const { rows } = await s.query<Mission>(
    `SELECT * FROM missions WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function listMissions(s: TenantSession, projectId?: string): Promise<Mission[]> {
  const { rows } = await s.query<Mission>(
    projectId
      ? `SELECT * FROM missions WHERE project_id = $1 ORDER BY created_at`
      : `SELECT * FROM missions ORDER BY created_at`,
    projectId ? [projectId] : undefined,
  );
  return rows;
}
