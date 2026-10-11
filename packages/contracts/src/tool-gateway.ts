import { z } from "zod";
import { uuidSchema } from "./ids";
import { ExplorerToolSchema } from "./explorer";

export const GatewayDecisionSchema = z.enum([
  "authorized",
  "denied"
]);

export const GatewayResultSchema = z.object({
  requestId: uuidSchema,
  tool: ExplorerToolSchema,
  decision: GatewayDecisionSchema,
  reason: z.string().max(500).optional(),
  policyId: z.string().max(200).optional(),
  occurredAt: z.coerce.date()
}).strict();

export type GatewayDecision = z.infer<typeof GatewayDecisionSchema>;
export type GatewayResult = z.infer<typeof GatewayResultSchema>;
