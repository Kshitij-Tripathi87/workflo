import { z } from "zod";
import { runIdSchema } from "./ids";

export const RunStateSchema = z.enum([
  "CREATED",
  "INGESTING",
  "PROVISIONING",
  "EXECUTING",
  "EXPLORING",
  "JUDGING",
  "NOTARIZING",
  "COMPLETED",
  "FAILED"
]);

export const RunSchema = z.object({
  runId: runIdSchema,
  state: RunStateSchema,
  createdAt: z.coerce.date(),
  updatedAt: z.coerce.date()
}).strict();

export type RunState = z.infer<typeof RunStateSchema>;
export type Run = z.infer<typeof RunSchema>;
