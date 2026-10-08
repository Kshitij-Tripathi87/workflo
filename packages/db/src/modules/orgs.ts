import type { TenantSession } from "../client";

/**
 * Class A — mutable control-plane resource.
 * Visibility is a membership of the current user (see RLS policy).
 */

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: Date;
  updated_at: Date;
}

export async function createOrganization(
  s: TenantSession,
  name: string,
  slug: string,
): Promise<Organization> {
  const { rows } = await s.query<Organization>(
    `INSERT INTO organizations (name, slug) VALUES ($1, $2) RETURNING *`,
    [name, slug],
  );
  return rows[0]!;
}

export async function renameOrganization(
  s: TenantSession,
  id: string,
  name: string,
): Promise<Organization | null> {
  const { rows } = await s.query<Organization>(
    `UPDATE organizations SET name = $2 WHERE id = $1 RETURNING *`,
    [id, name],
  );
  return rows[0] ?? null;
}

export async function getOrganization(
  s: TenantSession,
  id: string,
): Promise<Organization | null> {
  const { rows } = await s.query<Organization>(
    `SELECT * FROM organizations WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function listMyOrganizations(s: TenantSession): Promise<Organization[]> {
  const { rows } = await s.query<Organization>(`SELECT * FROM organizations ORDER BY created_at`);
  return rows;
}
