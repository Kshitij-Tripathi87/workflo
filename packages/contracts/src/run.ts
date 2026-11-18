import { z } from "zod";
import { LegacyRunSchema, LegacyRunStateSchema } from "./legacy-run";
import type { LegacyRun, LegacyRunState } from "./legacy-run";

// Mirrors of workflo_schema.contracts, checked against the exported JSON
// Schemas and Python golden records. Transition rules are not authored here.
export const LifecycleStateSchema = z.enum([
  "CREATED",
  "ADMITTED",
  "PROVISIONING",
  "SOURCE_ACQUISITION",
  "PREPARING",
  "EXECUTING",
  "EVALUATING",
  "COLLECTING_EVIDENCE",
  "TEARDOWN",
  "VERIFYING_TEARDOWN",
  "SIGNING",
  "COMPLETED",
  "INFRASTRUCTURE_FAILED",
  "EXECUTION_FAILED",
  "TEARDOWN_FAILED",
  "ATTESTATION_FAILED",
  "REJECTED",
  "CANCEL_REQUESTED",
]);

const ComponentVerificationSchema = z.enum([
  "verified",
  "failed",
  "incomplete",
  "not_applicable",
]);

// Validate serialized JSON, not the full range of Python input coercions.
export const RunOutcomeV1Schema = z
  .object({
    schema_version: z.string().default("1"),
    execution_status: z.enum([
      "completed",
      "rejected",
      "infrastructure_failed",
      "execution_failed",
      "teardown_failed",
      "attestation_failed",
    ]),
    cancelled: z.boolean().default(false),
    qa_verdict: z.enum([
      "pass",
      "fail",
      "warn",
      "inconclusive",
      "not_applicable",
    ]),
    trust_status: z.enum([
      "verified_clean",
      "verification_failed",
      "cleanup_incomplete",
      "unknown",
    ]),
    evidence_validation: ComponentVerificationSchema,
    teardown_verification: ComponentVerificationSchema,
    receipt_status: ComponentVerificationSchema,
  })
  .strict()
  .superRefine((outcome, ctx) => {
    if (outcome.execution_status === "completed") {
      if (outcome.teardown_verification !== "verified") {
        ctx.addIssue({
          code: "custom",
          path: ["teardown_verification"],
          message: "Completion requires verified teardown",
        });
      }
      if (outcome.receipt_status !== "verified") {
        ctx.addIssue({
          code: "custom",
          path: ["receipt_status"],
          message: "Completion requires a verified receipt",
        });
      }
      if (outcome.trust_status === "unknown") {
        ctx.addIssue({
          code: "custom",
          path: ["trust_status"],
          message: "Completion cannot have unknown trust status",
        });
      }
    }
    if (
      outcome.execution_status === "teardown_failed" &&
      outcome.teardown_verification === "verified"
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["teardown_verification"],
        message: "Teardown failure cannot have verified teardown",
      });
    }
  });

export type LifecycleState = z.infer<typeof LifecycleStateSchema>;
export type RunOutcomeV1 = z.infer<typeof RunOutcomeV1Schema>;

// Keep the original exports source-compatible for the legacy TS stack.
export { LegacyRunSchema, LegacyRunStateSchema } from "./legacy-run";
export type { LegacyRun, LegacyRunState } from "./legacy-run";

/** @deprecated Legacy DB states only. Use LifecycleStateSchema for new product contracts. */
export const RunStateSchema = LegacyRunStateSchema;
/** @deprecated Legacy DB row shape, not a Workflo product contract. */
export const RunSchema = LegacyRunSchema;
/** @deprecated Use LifecycleState for new product contracts. */
export type RunState = LegacyRunState;
/** @deprecated Legacy DB row shape, not a Workflo product contract. */
export type Run = LegacyRun;
