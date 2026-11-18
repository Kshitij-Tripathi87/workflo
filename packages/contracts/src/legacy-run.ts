import { z } from "zod";
import { runIdSchema } from "./ids";

// Compatibility with packages/db's original run_state and transition graph.
// Do not add product lifecycle states here (ADR-0017).
export const LegacyRunStateSchema = z.enum([
  "CREATED",
  "INGESTING",
  "PROVISIONING",
  "EXECUTING",
  "EXPLORING",
  "JUDGING",
  "NOTARIZING",
  "COMPLETED",
  "FAILED",
]);

export const LegacyRunSchema = z
  .object({
    runId: runIdSchema,
    state: LegacyRunStateSchema,
    createdAt: z.coerce.date(),
    updatedAt: z.coerce.date(),
  })
  .strict();

export type LegacyRunState = z.infer<typeof LegacyRunStateSchema>;
export type LegacyRun = z.infer<typeof LegacyRunSchema>;
