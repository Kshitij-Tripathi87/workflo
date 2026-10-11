import { describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { appDb, makeTenantFixture, GENESIS_HASH } from "./helpers";
import { evidence, inferenceUsage, runs } from "../src";
import { AuditLog } from "../src";
import { APP_URL } from "./helpers";

describe("inference_usage telemetry", () => {
  it("records measurements; rejects negative values", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "usage");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });

        const row = await inferenceUsage.recordInferenceUsage(s, {
          projectId: t.projectId,
          runId: run.id,
          modelId: "qwen3-4b-4bit",
          requestId: "req-1",
          inputTokens: 100,
          outputTokens: 40,
          inferenceSeconds: 1.25,
          queueSeconds: 0.3,
        });
        expect(row.model_id).toBe("qwen3-4b-4bit");

        await expect(
          inferenceUsage.recordInferenceUsage(s, {
            projectId: t.projectId,
            runId: run.id,
            modelId: "qwen3-4b-4bit",
            requestId: "req-2",
            inputTokens: -1,
            outputTokens: 0,
            inferenceSeconds: 0,
          }),
        ).rejects.toThrow(/violates check constraint/i);
        return null;
      });
    } finally {
      await db.close();
    }
  });
});

describe("audit log durability", () => {
  it("survives a caller transaction rollback (denied ops remain recorded)", async () => {
    const db = appDb();
    const audit = new AuditLog(APP_URL);
    try {
      const t = await makeTenantFixture(db, "audit-rollback");

      // Simulate: the caller's transaction FAILS and rolls back, but the
      // denial audit entry (separate connection) must persist.
      await expect(
        db.withTenant(t.ctx, async (s) => {
          await s.query(
            `INSERT INTO runs (organization_id, project_id, mission_id)
             VALUES ($1,$2,$3)`,
            [t.orgId, t.projectId, t.missionId],
          );
          throw new Error("caller rollback");
        }),
      ).rejects.toThrow(/caller rollback/);

      const auditId = await audit.write(
        { orgId: t.orgId, userId: t.userId, projectId: t.projectId },
        {
          actorLabel: "tool-gateway",
          action: "http_request",
          resourceType: "policy",
          outcome: "denied",
          metadata: { reason: "external URL" },
        },
      );
      expect(auditId).toBeTruthy();

      await db.withTenant(t.ctx, async (s) => {
        const { rows } = await s.query<{ outcome: string }>(
          `SELECT outcome FROM audit_logs WHERE id = $1`,
          [auditId],
        );
        expect(rows[0]!.outcome).toBe("denied");
        // The rolled-back run is gone; the denial record remains.
        const { rows: runRows } = await s.query(`SELECT id FROM runs`);
        expect(runRows).toHaveLength(0);
        return null;
      });
    } finally {
      await audit.close();
      await db.close();
    }
  });
});

describe("evidence/events contract alignment", () => {
  it("rejects payloads that violate PublicAgentEventSchema limits", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "evidence-contract");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });
        const base = {
          eventId: randomUUID(),
          runId: run.id,
          runSeq: 1,
          prevHash: GENESIS_HASH,
          hash: "deadbeef",
          occurredAt: new Date(),
        };

        await expect(
          evidence.appendEvent(s, {
            ...base,
            kind: "OBSERVATION",
            role: "EXPLORER",
            status: "info",
            summary: "x".repeat(501),
          }),
        ).rejects.toThrow();

        await expect(
          evidence.appendEvent(s, {
            ...base,
            kind: "NOT_A_KIND" as never,
            role: "EXPLORER",
            status: "info",
            summary: "ok",
          }),
        ).rejects.toThrow();

        // CoT-style extra fields never enter the ledger path.
        await expect(
          evidence.appendEvent(s, {
            ...base,
            kind: "OBSERVATION",
            role: "EXPLORER",
            status: "info",
            summary: "ok",
            ...({ thought: "hidden reasoning" } as object),
          } as never),
        ).rejects.toThrow();
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
