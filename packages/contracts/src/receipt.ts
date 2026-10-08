import { z } from "zod";
import { runIdSchema } from "./ids";

export const RepositoryProvenanceSchema = z.object({
  provider: z.literal("github"),
  url: z.string().url(),
  ref: z.string(),
  commit_sha: z.string(),
  tree_digest: z.string().optional()
}).strict();

export const InferenceProvenanceSchema = z.object({
  model_id: z.string(),
  request_ids: z.array(z.string()),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  inference_seconds: z.number().nonnegative(),
  source_code_included: z.boolean()
}).strict();

export const TransparencyProofSchema = z.object({
  log_id: z.string(),
  checkpoint: z.number().int().nonnegative(),
  merkle_root: z.string(),
  inclusion_proof: z.array(z.string())
}).strict();

export const ReceiptV4Schema = z.object({
  receipt_version: z.literal(4),
  run_id: runIdSchema,
  sandbox_id: z.string(),
  issued_at: z.coerce.date(),
  repository: RepositoryProvenanceSchema,
  mission: z.string(),
  run_report: z.object({
    lifecycle: z.string(),
    tests: z.record(z.unknown()),
    findings: z.array(z.unknown())
  }).strict(),
  agent_activity: z.array(z.unknown()),
  evidence: z.object({
    ledger_root: z.string()
  }).strict(),
  sandbox: z.object({
    isolation_attestation: z.record(z.unknown()),
    teardown_proof: z.record(z.unknown()),
    canary_check: z.record(z.unknown())
  }).strict(),
  inference_provenance: InferenceProvenanceSchema,
  transparency: TransparencyProofSchema
}).strict();

export type RepositoryProvenance = z.infer<typeof RepositoryProvenanceSchema>;
export type InferenceProvenance = z.infer<typeof InferenceProvenanceSchema>;
export type TransparencyProof = z.infer<typeof TransparencyProofSchema>;
export type ReceiptV4 = z.infer<typeof ReceiptV4Schema>;
