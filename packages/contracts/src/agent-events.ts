import { z } from "zod";
import { eventIdSchema, runIdSchema } from "./ids";

export const AgentRoleSchema = z.enum([
  "ORCHESTRATOR",
  "PROVISIONER",
  "INGESTOR",
  "EXECUTOR",
  "EXPLORER",
  "TOOL_GATEWAY",
  "JUDGE",
  "NOTARY"
]);

export const AgentEventKindSchema = z.enum([
  "MISSION_ACCEPTED",
  "STATE_CHANGE",
  "REPO_INGESTED",
  "SANDBOX_PROVISIONED",
  "APP_STARTED",
  "APP_HEALTHY",
  "TEST_RESULTS",
  "TOOL_PROPOSED",
  "TOOL_AUTHORIZED",
  "TOOL_DENIED",
  "TOOL_EXECUTED",
  "OBSERVATION",
  "HYPOTHESIS",
  "REPRODUCTION",
  "CONTROL",
  "FINDING_CONFIRMED",
  "FINDING_UNCONFIRMED",
  "RECEIPT_SIGNED",
  "TEARDOWN_VERIFIED",
  "RUN_FAILED"
]);

export const AgentEventStatusSchema = z.enum([
  "info",
  "success",
  "denied",
  "error",
  "timeout"
]);

/**
 * Public event contract.
 *
 * This schema intentionally excludes hidden chain-of-thought.
 * Only execution-relevant fields are allowed.
 */
export const PublicAgentEventSchema = z.object({
  eventId: eventIdSchema,
  runId: runIdSchema,
  parentEventId: eventIdSchema.nullable(),
  role: AgentRoleSchema,
  kind: AgentEventKindSchema,
  status: AgentEventStatusSchema,
  action: z.string().max(200).optional(),
  summary: z.string().max(500),
  rationale: z.string().max(500).optional(),
  observationSummary: z.string().max(2000).optional(),
  policyId: z.string().max(200).optional(),
  requestId: z.string().uuid().optional(),
  occurredAt: z.coerce.date()
}).strict();

export type AgentRole = z.infer<typeof AgentRoleSchema>;
export type AgentEventKind = z.infer<typeof AgentEventKindSchema>;
export type AgentEventStatus = z.infer<typeof AgentEventStatusSchema>;
export type PublicAgentEvent = z.infer<typeof PublicAgentEventSchema>;
