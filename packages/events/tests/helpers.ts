import { randomUUID } from "node:crypto";
import { Db, type TenantContext, type TenantSession } from "@workflo/db";
import { PG_PORT } from "./global-setup";

export const SUPER_URL = `postgres://postgres:postgres@127.0.0.1:${PG_PORT}/workflo_events_test`;
export const APP_URL = `postgres://workflo_app:workflo@127.0.0.1:${PG_PORT}/workflo_events_test`;

export function appDb(): Db {
  return Db.fromUrl(APP_URL, { max: 8 });
}

export function superDb(): Db {
  return Db.fromUrl(SUPER_URL, { max: 4 });
}

export interface TenantFixture {
  ctx: TenantContext & { projectId: string };
  orgId: string;
  userId: string;
  projectId: string;
  missionId: string;
  runId: string;
}

export async function makeRunFixture(db: Db, label: string): Promise<TenantFixture> {
  const userId = randomUUID();
  const slug = `${label}-${randomUUID().slice(0, 8)}`;

  const sysDb = superDb();
  let orgId: string;
  try {
    orgId = await sysDb.system(async (client) => {
      const { rows: orgRows } = await client.query<{ id: string }>(
        `INSERT INTO organizations (name, slug) VALUES ($1, $2) RETURNING id`,
        [label, slug],
      );
      await client.query(
        `INSERT INTO users (id, email, display_name) VALUES ($1, $2, $3)`,
        [userId, `${slug}@example.com`, label],
      );
      return orgRows[0]!.id;
    });
  } finally {
    await sysDb.close();
  }

  const base: TenantContext = { orgId, userId };

  const ids = await db.withTenant(base, async (s: TenantSession) => {
    await s.query(
      `INSERT INTO memberships (organization_id, user_id, role) VALUES ($1, $2, 'owner')`,
      [orgId, userId],
    );
    const { rows: proj } = await s.query<{ id: string }>(
      `INSERT INTO projects (organization_id, name, slug) VALUES ($1, $2, $3) RETURNING id`,
      [orgId, `${label}-proj`, `p-${randomUUID().slice(0, 8)}`],
    );
    const { rows: miss } = await s.query<{ id: string }>(
      `INSERT INTO missions (organization_id, project_id, title, intent)
       VALUES ($1, $2, $3, $4) RETURNING id`,
      [orgId, proj[0]!.id, `${label}-mission`, "verify"],
    );
    const { rows: run } = await s.query<{ id: string }>(
      `INSERT INTO runs (organization_id, project_id, mission_id)
       VALUES ($1, $2, $3) RETURNING id`,
      [orgId, proj[0]!.id, miss[0]!.id],
    );
    return { projectId: proj[0]!.id, missionId: miss[0]!.id, runId: run[0]!.id };
  });

  return {
    ctx: { ...base, projectId: ids.projectId },
    orgId,
    userId,
    ...ids,
  };
}
