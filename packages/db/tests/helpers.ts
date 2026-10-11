import { randomUUID, createHash } from "node:crypto";
import type { TenantSession } from "../src/client";
import { Db, evidence, type TenantContext } from "../src";

export const GENESIS_HASH = createHash("sha256")
  .update("workflo:evidence:genesis:v1")
  .digest("hex");

export const PG_PORT = 55632;
export const SUPER_URL = `postgres://postgres:postgres@127.0.0.1:${PG_PORT}/workflo_test`;
export const APP_URL = `postgres://workflo_app:workflo@127.0.0.1:${PG_PORT}/workflo_test`;

export function appDb(): Db {
  return Db.fromUrl(APP_URL, { max: 4 });
}

export function superDb(): Db {
  return Db.fromUrl(SUPER_URL, { max: 2 });
}

/**
 * Test fixture: org + user (as owner) + project + mission.
 *
 * Org/user bootstrap are service-level writes performed as superuser (RLS
 * correctly hides un-affiliated rows from the app role); then everything
 * else runs inside tenant context through the app role.
 */
export async function makeTenantFixture(db: Db, label: string) {
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

  const ctx: TenantContext = { orgId, userId };

  await db.withTenant(ctx, async (s) => {
    await s.query(
      `INSERT INTO memberships (organization_id, user_id, role)
       VALUES ($1, $2, 'owner')`,
      [ctx.orgId, userId],
    );
    return null;
  });

  const project = await db.withTenant(ctx, async (s) => {
    const { rows } = await s.query<{ id: string }>(
      `INSERT INTO projects (organization_id, name, slug)
       VALUES ($1, $2, $3) RETURNING id`,
      [ctx.orgId, `${label}-proj`, `p-${randomUUID().slice(0, 8)}`],
    );
    return rows[0]!;
  });

  const mission = await db.withTenant(ctx, async (s) => {
    const { rows } = await s.query<{ id: string }>(
      `INSERT INTO missions (organization_id, project_id, created_by, title, intent)
       VALUES ($1, $2, $3, $4, $5) RETURNING id`,
      [ctx.orgId, project.id, userId, `${label}-mission`, "verify things"],
    );
    return rows[0]!;
  });

  return { ctx, orgId, userId, projectId: project.id, missionId: mission.id };
}

/**
 * Test helper: append one event through the chained (authoritative) path.
 * Computes fake-but-well-formed sequential links against the current head
 * (sufficient for db-layer tests; real hashing lives in @workflo/events).
 */
export async function appendChainedEvent(
  s: TenantSession,
  t: { projectId: string },
  runId: string,
  fields: {
    kind: Parameters<typeof evidence.appendEvent>[1]["kind"];
    role: Parameters<typeof evidence.appendEvent>[1]["role"];
    status?: Parameters<typeof evidence.appendEvent>[1]["status"];
    summary: string;
  },
) {
  const latest = await evidence.latestChainedEvent(s, runId);
  const runSeq = (Number(latest?.run_seq ?? "0") || 0) + 1;
  const prevHash = latest?.hash ?? GENESIS_HASH;
  return evidence.appendEvent(s, {
    eventId: randomUUID(),
    runId,
    runSeq,
    prevHash,
    hash: `h${runSeq}-${randomUUID().slice(0, 8)}`,
    kind: fields.kind,
    role: fields.role,
    status: fields.status ?? "info",
    summary: fields.summary,
    occurredAt: new Date(),
  });
}

export function expectErr(error: unknown, pattern: RegExp | string): void {
  if (!(error instanceof Error)) {
    throw new Error(`expected error matching ${String(pattern)}, got non-error`);
  }
  const match =
    typeof pattern === "string" ? error.message.includes(pattern) : pattern.test(error.message);
  if (!match) {
    throw new Error(
      `expected error matching ${String(pattern)}, got: ${error.message}`,
    );
  }
}
