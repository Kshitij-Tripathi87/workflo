import { z } from "zod";
import { eventIdSchema } from "./ids";

export const JudgeVerdictSchema = z.enum([
  "CONFIRMED",
  "UNCONFIRMED",
  "INSUFFICIENT_CONTROL",
  "ERROR"
]);

export const JudgeDecisionSchema = z.object({
  findingId: z.string().uuid().optional(),
  title: z.string().max(300).optional(),
  summary: z.string().max(2000).optional(),
  verdict: JudgeVerdictSchema,
  confidence: z.enum(["low", "medium", "high"]).optional(),
  evidenceRefs: z.array(eventIdSchema).default([]),
  decidedAt: z.coerce.date()
}).strict();

export type JudgeVerdict = z.infer<typeof JudgeVerdictSchema>;
export type JudgeDecision = z.infer<typeof JudgeDecisionSchema>;
