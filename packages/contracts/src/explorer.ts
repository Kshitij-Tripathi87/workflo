import { z } from "zod";

export const ExplorerToolSchema = z.enum([
  "http_request",
  "read_app_logs",
  "browser_probe"
]);

export const HttpMethodSchema = z.enum([
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS"
]);

export const HttpRequestArgsSchema = z.object({
  method: HttpMethodSchema,
  path: z
    .string()
    .regex(/^\/[a-zA-Z0-9\-._~:/?#@!$&'()*+,;=%[\]]*$/, "path must be relative")
    .refine((p) => !p.startsWith("//"), { message: "scheme-relative URLs not allowed" }),
  headers: z.record(z.string()).optional(),
  body: z.unknown().optional()
}).strict();

export const ReadAppLogsArgsSchema = z.object({
  tail: z.number().int().positive().max(500).optional(),
  filter: z.string().max(200).optional()
}).strict();

export const BrowserProbeArgsSchema = z.object({
  action: z.string().max(200),
  target: z.string().max(500).optional()
}).strict();

export const ExplorerActionSchema = z.discriminatedUnion("tool", [
  z.object({
    tool: z.literal("http_request"),
    arguments: HttpRequestArgsSchema
  }),
  z.object({
    tool: z.literal("read_app_logs"),
    arguments: ReadAppLogsArgsSchema
  }),
  z.object({
    tool: z.literal("browser_probe"),
    arguments: BrowserProbeArgsSchema
  })
]);

/**
 * Explorer must return only a structured proposal.
 * No free-form execution claims.
 * No hidden chain-of-thought.
 */
export const ExplorerProposalSchema = z.object({
  action: ExplorerActionSchema,
  rationale: z.string().max(500),
  expected_signal: z.string().max(500)
}).strict();

export type ExplorerTool = z.infer<typeof ExplorerToolSchema>;
export type ExplorerAction = z.infer<typeof ExplorerActionSchema>;
export type ExplorerProposal = z.infer<typeof ExplorerProposalSchema>;
