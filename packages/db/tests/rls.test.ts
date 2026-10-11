import { describe, expect, it } from "vitest";
import { appDb, expectErr, makeTenantFixture, appendChainedEvent } from "./helpers";

describe("RLS tenant isolation", () => {
  it("tenant A sees own project", async () => {
    const db = appDb();
    try {
      const a = await makeTenantFixture(db, "rls-a-own");
      await db.withTenant(a.ctx, async (s) => {
        const { rows } = await s.query(
          `SELECT id FROM projects WHERE id = $1`,
          [a.projectId],
        );
        expect(rows).toHaveLength(1);
      });
    } finally {
      await db.close();
    }
  });

  it("tenant A cannot see tenant B projects/runs/findings/receipts/audit", async () => {
    const db = appDb();
    try {
      const a = await makeTenantFixture(db, "rls-a");
      const b = await makeTenantFixture(db, "rls-b");

      // Seed fixture data for B.
      await db.withTenant(b.ctx, async (s) => {
        const { rows: runRows } = await s.query<{ id: string }>(
          `INSERT INTO runs (organization_id, project_id, mission_id)
           VALUES ($1,$2,$3) RETURNING id`,
          [b.orgId, b.projectId, b.missionId],
        );
        const runId = runRows[0]!.id;
        await appendChainedEvent(s, b, runId, {
          kind: "MISSION_ACCEPTED",
          role: "ORCHESTRATOR",
          summary: "m",
        });
        await s.query(
          `INSERT INTO findings (organization_id, project_id, run_id, title)
           VALUES ($1,$2,$3,'b finding')`,
          [b.orgId, b.projectId, runId],
        );
        await s.query(
          `INSERT INTO audit_logs
            (organization_id, project_id, actor_label, action, resource_type, outcome)
           VALUES ($1,$2,'tester','x','run','success')`,
          [b.orgId, b.projectId],
        );
        // receipt (minimal contract-valid payload)
        await s.query(
          `INSERT INTO receipts
            (organization_id, project_id, run_id, receipt_version, payload,
             payload_sha256, signature, key_id, issued_at)
           VALUES ($1,$2,$3,4,'{}'::jsonb,repeat('0',64),'sig','key',now())`,
          [b.orgId, b.projectId, runId],
        );
        return null;
      });

      // Tenant A must see NOTHING of tenant B across all tenant-owned tables.
      await db.withTenant(a.ctx, async (s) => {
        const checks: Array<[string, string]> = [
          ["projects", a.projectId],
          ["runs", a.missionId],
          ["evidence_events", a.projectId],
          ["findings", a.projectId],
          ["receipts", a.projectId],
          ["audit_logs", a.projectId],
          ["inference_usage", a.projectId],
          ["missions", a.missionId],
          ["github_connections", a.orgId],
        ];
        for (const [table, key] of checks) {
          const { rows } = await s.query(
            `SELECT count(*)::int AS n FROM ${table} WHERE organization_id <> $1`,
            [key.startsWith("proj") ? key : a.orgId],
          );
          expect(rows[0]!.n, `${table} leaked cross-tenant rows`).toBe(0);
        }

        // Direct id-based cross-tenant reads must return nothing.
        const { rows: bProjects } = await s.query(
          `SELECT id FROM projects WHERE id = $1`,
          [b.projectId],
        );
        expect(bProjects).toHaveLength(0);

        const { rows: bMissions } = await s.query(
          `SELECT id FROM missions WHERE id = $1`,
          [b.missionId],
        );
        expect(bMissions).toHaveLength(0);

        const { rows: bFindings } = await s.query(`SELECT id FROM findings`);
        expect(bFindings).toHaveLength(0);

        const { rows: bReceipts } = await s.query(`SELECT id FROM receipts`);
        expect(bReceipts).toHaveLength(0);

        const { rows: bAudit } = await s.query(`SELECT id FROM audit_logs`);
        expect(bAudit).toHaveLength(0);

        const { rows: bEvidence } = await s.query(`SELECT id FROM evidence_events`);
        expect(bEvidence).toHaveLength(0);
      });

      // Cross-tenant INSERT must be rejected (RLS WITH CHECK).
      await db.withTenant(a.ctx, async (s) => {
        try {
          await s.query(
            `INSERT INTO projects (organization_id, name, slug)
             VALUES ($1, 'evil', 'evil')`,
            [b.orgId],
          );
          throw new Error("should have failed");
        } catch (error) {
          expectErr(error, /row-level security|row violates/i);
        }
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("missing tenant context fails closed (zero rows everywhere)", async () => {
    const db = appDb();
    try {
      const a = await makeTenantFixture(db, "rls-empty-ctx");
      await db.withTenant(a.ctx, async (s) => {
        await s.query(
          `INSERT INTO runs (organization_id, project_id, mission_id)
           VALUES ($1,$2,$3)`,
          [a.orgId, a.projectId, a.missionId],
        );
        return null;
      });

      await db.system(async (client) => {
        // workflo_app with NO GUCs: SELECT returns nothing, not everything.
        const { rows } = await client.query(`SELECT count(*)::int AS n FROM runs`);
        expect(rows[0]!.n).toBe(0);
        const { rows: projRows } = await client.query(`SELECT count(*)::int AS n FROM projects`);
        expect(projRows[0]!.n).toBe(0);

        // INSERT without tenant context is rejected.
        try {
          await client.query(
            `INSERT INTO projects (organization_id, name, slug)
             VALUES ($1, 'x', 'x')`,
            [a.orgId],
          );
          throw new Error("should have failed");
        } catch (error) {
          expectErr(error, /row-level security|row violates/i);
        }
      });
    } finally {
      await db.close();
    }
  });

  it("users are not visible across orgs", async () => {
    const db = appDb();
    try {
      const a = await makeTenantFixture(db, "rls-users-a");
      const b = await makeTenantFixture(db, "rls-users-b");

      await db.withTenant(a.ctx, async (s) => {
        const { rows } = await s.query(`SELECT id FROM users WHERE id = $1`, [b.userId]);
        expect(rows).toHaveLength(0);
        const { rows: self } = await s.query(`SELECT id FROM users WHERE id = $1`, [a.userId]);
        expect(self).toHaveLength(1);
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
