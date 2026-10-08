import { createHash } from "node:crypto";
import { ReceiptV4Schema, type ReceiptV4 } from "@workflo/contracts";
import type { TenantSession } from "../client";

/**
 * Class D — immutable cryptographic artifact.
 *
 * Receipts are produced by packages/notary (Day 8) after the evidence ledger
 * is complete. They are validated against ReceiptV4Schema before INSERT and
 * are never updated or deleted (privileges + trigger).
 */

export interface ReceiptRow {
  id: string;
  organization_id: string;
  project_id: string;
  run_id: string;
  receipt_version: number;
  payload: ReceiptV4;
  payload_sha256: string;
  signature: string;
  key_id: string;
  log_id: string | null;
  log_checkpoint: string | null;
  merkle_root: string | null;
  issued_at: Date;
  created_at: Date;
}

export interface StoreReceiptInput {
  projectId: string;
  payload: ReceiptV4;
  signature: string;
  keyId: string;
}

/** Validates the payload against the frozen ReceiptV4 contract, then stores. */
export async function storeReceipt(
  s: TenantSession,
  input: StoreReceiptInput,
): Promise<ReceiptRow> {
  const payload = ReceiptV4Schema.parse(input.payload);
  const payloadSha256 = createHash("sha256")
    .update(JSON.stringify(payload))
    .digest("hex");

  const { rows } = await s.query<ReceiptRow>(
    `INSERT INTO receipts
      (organization_id, project_id, run_id, receipt_version, payload,
       payload_sha256, signature, key_id, log_id, log_checkpoint, merkle_root,
       issued_at)
     VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11,$12)
     RETURNING *`,
    [
      s.ctx.orgId,
      input.projectId,
      payload.run_id,
      payload.receipt_version,
      JSON.stringify(payload),
      payloadSha256,
      input.signature,
      input.keyId,
      payload.transparency.log_id,
      payload.transparency.checkpoint,
      payload.transparency.merkle_root,
      payload.issued_at,
    ],
  );
  return rows[0]!;
}

export async function getReceipt(s: TenantSession, id: string): Promise<ReceiptRow | null> {
  const { rows } = await s.query<ReceiptRow>(
    `SELECT * FROM receipts WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function getReceiptForRun(s: TenantSession, runId: string): Promise<ReceiptRow | null> {
  const { rows } = await s.query<ReceiptRow>(
    `SELECT * FROM receipts WHERE run_id = $1`,
    [runId],
  );
  return rows[0] ?? null;
}
