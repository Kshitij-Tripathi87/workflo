import pg from "pg";
import { parseTenantContext, TenantGuc, type TenantContext } from "../rls";

const { Pool } = pg;

/**
 * Class C — append-only audit log.
 *
 * Security-sensitive operations (auth, key use, policy denial, secrets access)
 * must leave a durable record EVEN IF the requesting transaction rolls back.
 * Therefore this module uses a dedicated pool and its own transaction per
 * write — a caller ROLLBACK cannot erase a completed audit entry.
 */
export class AuditLog {
  private readonly pool: pg.Pool;

  constructor(connectionString: string) {
    this.pool = new Pool({ connectionString, max: 2 });
  }

  async write(
    ctx: TenantContext & { projectId?: string },
    entry: {
      actorUserId?: string;
      actorLabel: string;
      action: string;
      resourceType: string;
      resourceId?: string;
      outcome: "success" | "denied" | "error";
      requestId?: string;
      metadata?: Record<string, unknown>;
    },
  ): Promise<string> {
    const parsed = parseTenantContext({ orgId: ctx.orgId, userId: ctx.userId });
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      await client.query(`SELECT set_config($1, $2, true)`, [
        TenantGuc.OrgId,
        parsed.orgId,
      ]);
      if (parsed.userId) {
        await client.query(`SELECT set_config($1, $2, true)`, [
          TenantGuc.UserId,
          parsed.userId,
        ]);
      }
      const { rows } = await client.query<{ id: string }>(
        `INSERT INTO audit_logs
          (organization_id, project_id, actor_user_id, actor_label, action,
           resource_type, resource_id, outcome, request_id, metadata)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
         RETURNING id`,
        [
          parsed.orgId,
          ctx.projectId ?? null,
          entry.actorUserId ?? null,
          entry.actorLabel,
          entry.action,
          entry.resourceType,
          entry.resourceId ?? null,
          entry.outcome,
          entry.requestId ?? null,
          JSON.stringify(entry.metadata ?? {}),
        ],
      );
      await client.query("COMMIT");
      return rows[0]!.id;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
