import type { TenantSession } from "../client";

/**
 * Class A — membership of a user in an organization (with org role).
 * INSERT requires tenant context (RLS WITH CHECK on organization_id).
 * Bootstrap flow: createOrganization (open INSERT), then addMembership with
 * tenant context set.
 */

export type MemberRole = "owner" | "admin" | "developer" | "viewer" | "auditor";

export interface Membership {
  id: string;
  organization_id: string;
  user_id: string;
  role: MemberRole;
  created_at: Date;
}

export async function addMembership(
  s: TenantSession,
  userId: string,
  role: MemberRole,
): Promise<Membership> {
  const { rows } = await s.query<Membership>(
    `INSERT INTO memberships (organization_id, user_id, role)
     VALUES ($1, $2, $3)
     ON CONFLICT (organization_id, user_id) DO UPDATE SET role = EXCLUDED.role
     RETURNING *`,
    [s.ctx.orgId, userId, role],
  );
  return rows[0]!;
}

export async function removeMembership(
  s: TenantSession,
  userId: string,
): Promise<boolean> {
  const { rowCount } = await s.query(
    `DELETE FROM memberships WHERE organization_id = $1 AND user_id = $2`,
    [s.ctx.orgId, userId],
  );
  return (rowCount ?? 0) > 0;
}

export async function listMemberships(s: TenantSession): Promise<Membership[]> {
  const { rows } = await s.query<Membership>(
    `SELECT * FROM memberships WHERE organization_id = $1 ORDER BY created_at`,
    [s.ctx.orgId],
  );
  return rows;
}
