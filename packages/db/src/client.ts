import pg from "pg";
import type { PoolClient, PoolConfig, QueryResultRow } from "pg";
import { parseTenantContext, TenantGuc, type TenantContext } from "./rls";

const { Pool } = pg;

/**
 * TenantSession is the ONLY handle module code may query through.
 * It is only obtainable via Db.withTenant(...), which binds the
 * transaction-local tenant GUCs before any query runs.
 */
export class TenantSession {
  constructor(
    readonly client: PoolClient,
    readonly ctx: TenantContext,
  ) {}

  /**
   * Each statement runs behind a SAVEPOINT so an expected error (policy
   * denial, illegal transition) rolls back only that statement instead of
   * poisoning the caller's whole transaction.
   */
  async query<T extends QueryResultRow = QueryResultRow>(
    text: string,
    values?: readonly unknown[],
  ) {
    await this.client.query("SAVEPOINT wfq_statement");
    try {
      return await this.client.query<T>(text, values as unknown[] | undefined);
    } catch (error) {
      await this.client.query("ROLLBACK TO SAVEPOINT wfq_statement");
      throw error;
    }
  }
}

export class Db {
  private constructor(readonly pool: pg.Pool) {}

  static fromUrl(connectionString: string, opts?: PoolConfig): Db {
    return new Db(new Pool({ connectionString, ...opts }));
  }

  static fromPool(pool: pg.Pool): Db {
    return new Db(pool);
  }

  /**
   * Run `fn` inside a transaction with tenant GUCs bound. The GUCs are
   * transaction-local (set_config(..., true)) and vanish on COMMIT/ROLLBACK,
   * so pooled clients can never leak tenant context.
   */
  async withTenant<T>(
    ctx: TenantContext,
    fn: (session: TenantSession) => Promise<T>,
  ): Promise<T> {
    const parsed = parseTenantContext(ctx);
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      await client.query(
        `SELECT set_config($1, $2, true)`,
        [TenantGuc.OrgId, parsed.orgId],
      );
      if (parsed.userId) {
        await client.query(
          `SELECT set_config($1, $2, true)`,
          [TenantGuc.UserId, parsed.userId],
        );
      }
      const result = await fn(new TenantSession(client, parsed));
      await client.query("COMMIT");
      return result;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  }

  /**
   * Run SQL with NO tenant context. Restricted to migrations and bootstrap
   * tasks. RLS denies all tenant rows here by design; callers must be
   * superuser/owner (workflo_app gets nothing past policies without context).
   */
  async system<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      return await fn(client);
    } finally {
      client.release();
    }
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
