import type { TenantSession } from "../client";

/**
 * Class A — GitHub connection metadata. `credentialRef` must be a pointer to
 * the secret material (vault://, kms://, sm://, file://), NEVER the token
 * itself. The database CHECK constraint rejects raw token formats.
 */

export interface GithubConnection {
  id: string;
  organization_id: string;
  project_id: string | null;
  provider: string;
  installation_id: string;
  repository_id: string | null;
  repository_url: string | null;
  account_login: string | null;
  default_ref: string | null;
  credential_ref: string;
  created_at: Date;
  updated_at: Date;
}

export interface NewGithubConnection {
  installationId: string;
  credentialRef: string;
  projectId?: string;
  repositoryId?: string;
  repositoryUrl?: string;
  accountLogin?: string;
  defaultRef?: string;
}

export async function createGithubConnection(
  s: TenantSession,
  input: NewGithubConnection,
): Promise<GithubConnection> {
  const { rows } = await s.query<GithubConnection>(
    `INSERT INTO github_connections
      (organization_id, project_id, installation_id, repository_id,
       repository_url, account_login, default_ref, credential_ref)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     RETURNING *`,
    [
      s.ctx.orgId,
      input.projectId ?? null,
      input.installationId,
      input.repositoryId ?? null,
      input.repositoryUrl ?? null,
      input.accountLogin ?? null,
      input.defaultRef ?? null,
      input.credentialRef,
    ],
  );
  return rows[0]!;
}

export async function getGithubConnection(
  s: TenantSession,
  id: string,
): Promise<GithubConnection | null> {
  const { rows } = await s.query<GithubConnection>(
    `SELECT * FROM github_connections WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function listGithubConnections(s: TenantSession): Promise<GithubConnection[]> {
  const { rows } = await s.query<GithubConnection>(
    `SELECT * FROM github_connections ORDER BY created_at`,
  );
  return rows;
}

export async function deleteGithubConnection(
  s: TenantSession,
  id: string,
): Promise<boolean> {
  const { rowCount } = await s.query(
    `DELETE FROM github_connections WHERE id = $1`,
    [id],
  );
  return (rowCount ?? 0) > 0;
}
