import { describe, expect, it } from "vitest";
import { appDb, expectErr, makeTenantFixture, superDb, appendChainedEvent } from "./helpers";

/**
 * Gate: evidence_events, audit_logs, inference_usage and receipts are
 * append-only / immutable at the DATABASE layer — both via revoked privileges
 * for the app role and via triggers for even privileged connections.
 */
describe("append-only enforcement", () => {
  it("app role cannot UPDATE/DELETE evidence_events, audit_logs, inference_usage, receipts", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "append-app");

      await db.withTenant(t.ctx, async (s) => {
        const { rows: runRows } = await s.query<{ id: string }>(
          `INSERT INTO runs (organization_id, project_id, mission_id)
           VALUES ($1,$2,$3) RETURNING id`,
          [t.orgId, t.projectId, t.missionId],
        );
        const runId = runRows[0]!.id;

        await appendChainedEvent(s, t, runId, {
          kind: "OBSERVATION",
          role: "EXECUTOR",
          summary: "ev",
        });
        await s.query(
          `INSERT INTO audit_logs (organization_id, actor_label, action, resource_type, outcome)
           VALUES ($1,'t','a','r','success')`,
          [t.orgId],
        );
        await s.query(
          `INSERT INTO inference_usage
            (organization_id, project_id, run_id, model_id, request_id,
             input_tokens, output_tokens, inference_seconds)
           VALUES ($1,$2,$3,'qwen3-4b-4bit','r1',1,1,0.1)`,
          [t.orgId, t.projectId, runId],
        );
        await s.query(
          `INSERT INTO receipts
            (organization_id, project_id, run_id, receipt_version, payload,
             payload_sha256, signature, key_id, issued_at)
           VALUES ($1,$2,$3,4,'{}'::jsonb,repeat('1',64),'sig','key',now())`,
          [t.orgId, t.projectId, runId],
        );

        for (const [table, op] of [
          ["evidence_events", "UPDATE"],
          ["evidence_events", "DELETE"],
          ["audit_logs", "UPDATE"],
          ["audit_logs", "DELETE"],
          ["inference_usage", "UPDATE"],
          ["inference_usage", "DELETE"],
          ["receipts", "UPDATE"],
          ["receipts", "DELETE"],
        ] as const) {
          const sql =
            op === "UPDATE"
              ? `UPDATE ${table} SET summary = 'x'`
              : `DELETE FROM ${table}`;
          try {
            await s.query(sql.replace("summary = 'x'", table === "audit_logs" ? "actor_label = 'x'" : table === "inference_usage" ? "model_id = 'x'" : table === "receipts" ? "signature = 'x'" : "summary = 'x'"));
            throw new Error(`${op} on ${table} should have failed`);
          } catch (error) {
            expectErr(error, /permission denied|append-only/i);
          }
        }
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("triggers block mutation even for the table owner (superuser)", async () => {
    const app = appDb();
    const infra = await makeTenantFixture(app, "append-owner-seed");
    await app.withTenant(infra.ctx, async (s) => {
      await s.query(
        `INSERT INTO runs (organization_id, project_id, mission_id) VALUES ($1,$2,$3)`,
        [infra.orgId, infra.projectId, infra.missionId],
      );
      return null;
    });
    await app.close();

    const db = superDb();
    try {
      const { rows: runRows } = await db.system((c) =>
        c.query<{ id: string }>(
          `SELECT id FROM runs WHERE organization_id = $1`,
          [infra.orgId],
        ),
      );
      const runId = runRows[0]!.id;

      await db.system((c) =>
        c.query(
          `INSERT INTO evidence_events
            (organization_id, project_id, run_id, event_type, role, status, summary, occurred_at)
           VALUES ($1,$2,$3,'OBSERVATION','EXECUTOR','info','ev',now())`,
          [infra.orgId, infra.projectId, runId],
        ),
      );

      for (const table of ["evidence_events", "audit_logs", "inference_usage", "receipts"]) {
        await expect(
          db.system((c) =>
            c.query(
              `UPDATE ${table} SET organization_id = organization_id`,
            ),
          ),
        ).rejects.toThrow(/append-only/);

        await expect(
          db.system((c) => c.query(`DELETE FROM ${table}`)),
        ).rejects.toThrow(/append-only/);
      }
    } finally {
      await db.close();
    }
  });

  it("appended evidence events keep seq ordering and hash links", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "append-seq");
      await db.withTenant(t.ctx, async (s) => {
        const { rows: runRows } = await s.query<{ id: string }>(
          `INSERT INTO runs (organization_id, project_id, mission_id)
           VALUES ($1,$2,$3) RETURNING id`,
          [t.orgId, t.projectId, t.missionId],
        );
        const runId = runRows[0]!.id;

        await appendChainedEvent(s, t, runId, {
          kind: "MISSION_ACCEPTED",
          role: "ORCHESTRATOR",
          summary: "one",
        });
        await appendChainedEvent(s, t, runId, {
          kind: "SANDBOX_PROVISIONED",
          role: "PROVISIONER",
          status: "success",
          summary: "two",
        });

        const { rows } = await s.query<{
          run_seq: string;
          hash: string | null;
          prev_hash: string | null;
        }>(
          `SELECT run_seq, hash, prev_hash FROM evidence_events
           WHERE run_id = $1 ORDER BY run_seq`,
          [runId],
        );
        expect(rows).toHaveLength(2);
        expect(Number(rows[0]!.run_seq)).toBe(1);
        expect(Number(rows[1]!.run_seq)).toBe(2);
        expect(rows[1]!.prev_hash).toBe(rows[0]!.hash);
        expect(rows[0]!.prev_hash).toBeTruthy();
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
