import { describe, expect, it } from "vitest";
import { ReceiptV4Schema, type ReceiptV4 } from "@workflo/contracts";
import { appDb, makeTenantFixture } from "./helpers";
import { receipts, runs } from "../src";

function validReceiptPayload(runId: string): ReceiptV4 {
  return ReceiptV4Schema.parse({
    receipt_version: 4,
    run_id: runId,
    sandbox_id: "sbx-01",
    issued_at: new Date().toISOString(),
    repository: {
      provider: "github",
      url: "https://github.com/org/repo",
      ref: "main",
      commit_sha: "abc123",
    },
    mission: "verify checkout",
    run_report: { lifecycle: "COMPLETED", tests: { passed: 1, failed: 0 }, findings: [] },
    agent_activity: [],
    evidence: { ledger_root: "sha256:ledger" },
    sandbox: {
      isolation_attestation: { netns: true },
      teardown_proof: { verified: true },
      canary_check: { blocked: true },
    },
    inference_provenance: {
      model_id: "qwen3-4b-4bit",
      request_ids: ["req-1"],
      input_tokens: 10,
      output_tokens: 5,
      inference_seconds: 1,
      source_code_included: false,
    },
    transparency: {
      log_id: "log-01",
      checkpoint: 1,
      merkle_root: "sha256:root",
      inclusion_proof: [],
    },
  });
}

describe("receipts: immutable cryptographic artifacts", () => {
  it("stores a contract-valid receipt and refuses a second one for the run", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "receipt-store");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });

        const stored = await receipts.storeReceipt(s, {
          projectId: t.projectId,
          payload: validReceiptPayload(run.id),
          signature: "c2ln",
          keyId: "dev-ed25519-01",
        });
        expect(stored.receipt_version).toBe(4);
        expect(stored.payload_sha256).toMatch(/^[a-f0-9]{64}$/);

        // One receipt per run, forever.
        await expect(
          receipts.storeReceipt(s, {
            projectId: t.projectId,
            payload: validReceiptPayload(run.id),
            signature: "b3RoZXI",
            keyId: "dev-ed25519-01",
          }),
        ).rejects.toThrow(/duplicate key/);
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("frontend cannot rewrite a receipt (no UPDATE/DELETE)", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "receipt-rewrite");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });
        await receipts.storeReceipt(s, {
          projectId: t.projectId,
          payload: validReceiptPayload(run.id),
          signature: "c2ln",
          keyId: "dev-ed25519-01",
        });

        await expect(
          s.query(`UPDATE receipts SET signature = 'hacked' WHERE run_id = $1`, [run.id]),
        ).rejects.toThrow(/permission denied|immutable|append-only/i);
        await expect(s.query(`DELETE FROM receipts`)).rejects.toThrow(
          /permission denied|immutable|append-only/i,
        );

        // And the stored payload still verifies against the contract.
        const r = await receipts.getReceiptForRun(s, run.id);
        expect(ReceiptV4Schema.safeParse(r!.payload).success).toBe(true);
        return null;
      });
    } finally {
      await db.close();
    }
  });

  it("rejects payloads that fail the ReceiptV4 contract", async () => {
    const db = appDb();
    try {
      const t = await makeTenantFixture(db, "receipt-contract");
      await db.withTenant(t.ctx, async (s) => {
        const run = await runs.createRun(s, {
          projectId: t.projectId,
          missionId: t.missionId,
        });
        await expect(
          receipts.storeReceipt(s, {
            projectId: t.projectId,
            payload: { ...validReceiptPayload(run.id), receipt_version: 3 } as unknown as ReceiptV4,
            signature: "c2ln",
            keyId: "dev",
          }),
        ).rejects.toThrow();
        return null;
      });
    } finally {
      await db.close();
    }
  });
});
