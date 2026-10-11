import type { TenantSession } from "../client";

/**
 * Class A — mutable control-plane resource (tenant-scoped).
 */

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string;
  status: "ACTIVE" | "ARCHIVED";
  created_at: Date;
  updated_at: Date;
}

export async function createProject(
  s: TenantSession,
  name: string,
  slug: string,
  description = "",
): Promise<Project> {
  const { rows } = await s.query<Project>(
    `INSERT INTO projects (organization_id, name, slug, description)
     VALUES ($1, $2, $3, $4) RETURNING *`,
    [s.ctx.orgId, name, slug, description],
  );
  return rows[0]!;
}

export async function getProject(s: TenantSession, id: string): Promise<Project | null> {
  const { rows } = await s.query<Project>(
    `SELECT * FROM projects WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function listProjects(s: TenantSession): Promise<Project[]> {
  const { rows } = await s.query<Project>(
    `SELECT * FROM projects ORDER BY created_at`,
  );
  return rows;
}

export async function archiveProject(
  s: TenantSession,
  id: string,
): Promise<Project | null> {
  const { rows } = await s.query<Project>(
    `UPDATE projects SET status = 'ARCHIVED' WHERE id = $1 RETURNING *`,
    [id],
  );
  return rows[0] ?? null;
}
