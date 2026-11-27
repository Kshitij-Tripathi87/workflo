import { z } from "zod";

const idSchema = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
const digestSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/);
const timestampSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
const creatorSchema = z.object({
  user_id: idSchema,
  organization_id: idSchema
}).strict();

export const AgenticRoleSchema = z.enum([
  "mission_supervisor", "ingestor", "executor", "explorer", "test_designer",
  "browser_probe", "security_probe", "judge", "notary"
]);
export const AgentTaskStatusSchema = z.enum([
  "pending", "ready", "running", "completed", "failed", "cancelled", "timed_out", "blocked"
]);
export const AgentActionKindSchema = z.enum([
  "proposed", "validated", "denied", "executed", "observed"
]);
export const AgentExecutionStatusSchema = z.enum([
  "running", "completed", "failed", "cancelled", "timed_out", "blocked"
]);
export const AgentArtifactKindSchema = z.enum([
  "test_proposal", "generated_test", "report", "observation", "model_provenance", "other"
]);
export const AgentToolEffectSchema = z.enum([
  "read_only", "sandbox_write", "network_read", "network_write"
]);
export const AgentFilesystemRootSchema = z.enum([
  "source_snapshot", "workspace", "generated_tests", "artifacts"
]);
export const AgentFilesystemAccessSchema = z.enum(["read", "write"]);

export const AgentBudgetV1Schema = z.object({
  max_tokens: z.number().int().min(0).max(2_000_000).default(0),
  max_inference_requests: z.number().int().min(0).max(10_000).default(0),
  max_tool_calls: z.number().int().min(0).max(100_000).default(0),
  max_parallel_tasks: z.number().int().min(1).max(16).default(1),
  max_elapsed_ms: z.number().int().min(1_000).max(86_400_000).default(60_000),
  max_cpu_ms: z.number().int().min(0).max(5_184_000_000).default(60_000),
  max_memory_mib: z.number().int().min(256).max(262_144).default(512),
  max_disk_mib: z.number().int().min(0).max(1_048_576).default(512),
  max_output_bytes: z.number().int().min(0).max(1_073_741_824).default(1_048_576),
  max_log_bytes: z.number().int().min(0).max(104_857_600).default(262_144),
  max_retries: z.number().int().min(0).max(10).default(0)
}).strict().superRefine((budget, ctx) => {
  if (budget.max_inference_requests > 0 && budget.max_tokens === 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["max_tokens"],
      message: "Inference requests require a non-zero token budget"
    });
  }
});

export const AgentProfileRefV1Schema = z.object({
  profile_id: idSchema,
  version: z.string().min(1).max(64),
  profile_digest: digestSchema
}).strict();

export const AgentProfileV1Schema = z.object({
  schema_version: z.string().default("1"),
  profile_id: idSchema,
  version: z.string().min(1).max(64),
  role: AgenticRoleSchema,
  runtime_bundle_digest: digestSchema,
  entrypoint: z.string().min(1).max(512).refine((value) =>
    !value.startsWith("/") &&
    !value.includes("\\") &&
    !value.includes(":") &&
    !value.split("/").some((part) => part === "" || part === "." || part === ".."),
    "Agent entrypoint must be a safe relative POSIX path"
  ),
  task_types: z.array(idSchema).min(1).max(32),
  input_schema_digest: digestSchema,
  output_schema_digest: digestSchema,
  tool_ids: z.array(idSchema).max(64).default([]),
  delegatable_roles: z.array(AgenticRoleSchema).max(8).default([]),
  model_profile_id: idSchema.nullable().default(null),
  model_artifact_digests: z.array(digestSchema).max(16).default([]),
  budget: AgentBudgetV1Schema,
  created_by: creatorSchema,
  created_at: timestampSchema
}).strict().superRefine((profile, ctx) => {
  const unique = (values: string[]) => new Set(values).size === values.length;
  if (!unique(profile.task_types)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["task_types"], message: "Task types must be unique" });
  }
  if (!unique(profile.tool_ids)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tool_ids"], message: "Tool IDs must be unique" });
  }
  if (!unique(profile.delegatable_roles)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["delegatable_roles"], message: "Delegatable roles must be unique" });
  }
  if (!unique(profile.model_artifact_digests)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["model_artifact_digests"], message: "Model digests must be unique" });
  }
  const usesModel = profile.budget.max_inference_requests > 0;
  if (usesModel && profile.model_profile_id === null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["model_profile_id"], message: "Inference-enabled profile requires a model profile" });
  }
  if (profile.model_profile_id !== null && profile.role !== "explorer") {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["role"], message: "Only Explorer may use a model in v1" });
  }
  if (profile.model_profile_id !== null && profile.model_artifact_digests.length === 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["model_artifact_digests"], message: "Model-enabled profile must pin model artifacts" });
  }
  if (profile.model_profile_id === null && profile.model_artifact_digests.length > 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["model_artifact_digests"], message: "Model artifacts require model_profile_id" });
  }
  if ((profile.role === "judge" || profile.role === "notary") && profile.tool_ids.length > 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tool_ids"], message: "Judge and Notary cannot receive direct tools" });
  }
});

export const AgentToolDefinitionV1Schema = z.object({
  tool_id: idSchema,
  version: z.string().min(1).max(64),
  request_schema_digest: digestSchema,
  response_schema_digest: digestSchema,
  effect: AgentToolEffectSchema,
  allowed_roles: z.array(AgenticRoleSchema).min(1).max(8),
  idempotent: z.boolean(),
  requires_approval: z.boolean().default(false)
}).strict().superRefine((tool, ctx) => {
  if (new Set(tool.allowed_roles).size !== tool.allowed_roles.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["allowed_roles"], message: "Allowed roles must be unique" });
  }
  if (tool.effect === "network_write" && !tool.requires_approval) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["requires_approval"], message: "Network-write tools require approval" });
  }
});

export const AgentProfileRegistryV1Schema = z.object({
  schema_version: z.string().default("1"),
  registry_id: idSchema,
  organization_id: idSchema,
  version: z.string().min(1).max(64),
  profiles: z.array(AgentProfileV1Schema).min(1).max(128),
  tools: z.array(AgentToolDefinitionV1Schema).max(256).default([]),
  revoked_profile_digests: z.array(digestSchema).max(512).default([]),
  created_by: creatorSchema,
  created_at: timestampSchema,
  signature: z.string().max(1024).nullable().default(null)
}).strict().superRefine((registry, ctx) => {
  if (registry.created_by.organization_id !== registry.organization_id) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["created_by"], message: "Registry creator tenant mismatch" });
  }
  if (new Set(registry.profiles.map((p) => p.profile_id + "|" + p.version)).size !== registry.profiles.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["profiles"], message: "Duplicate profile version" });
  }
  if (new Set(registry.tools.map((t) => t.tool_id)).size !== registry.tools.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tools"], message: "Duplicate tool ID" });
  }
  if (new Set(registry.revoked_profile_digests).size !== registry.revoked_profile_digests.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["revoked_profile_digests"], message: "Duplicate revocation digest" });
  }
  const toolsById = new Map(registry.tools.map((tool) => [tool.tool_id, tool]));
  registry.profiles.forEach((profile, index) => {
    profile.tool_ids.forEach((toolId) => {
      const registered = toolsById.get(toolId);
      if (!registered) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["profiles", index, "tool_ids"], message: "Profile references an unknown tool" });
      } else if (!registered.allowed_roles.includes(profile.role)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["profiles", index, "tool_ids"], message: "Tool is not allowed for this role" });
      }
    });
  });
});

export const AgenticMissionV1Schema = z.object({
  schema_version: z.string().default("1"),
  mission_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  source_commit: z.string().regex(/^[0-9a-f]{7,64}$/),
  policy_digest: digestSchema,
  registry_digest: digestSchema,
  task_type: idSchema,
  objective: z.string().min(5).max(2_000),
  profiles: z.array(AgentProfileRefV1Schema).min(1).max(16),
  budget: AgentBudgetV1Schema,
  idempotency_key: z.string().min(8).max(128),
  created_by: creatorSchema,
  created_at: timestampSchema
}).strict().superRefine((mission, ctx) => {
  if (mission.created_by.organization_id !== mission.organization_id) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["created_by"], message: "Mission creator tenant mismatch" });
  }
  if (new Set(mission.profiles.map((p) => p.profile_id + "|" + p.version)).size !== mission.profiles.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["profiles"], message: "Duplicate profile reference" });
  }
});

export const AgentTaskV1Schema = z.object({
  task_id: idSchema,
  task_type: idSchema,
  role: AgenticRoleSchema,
  profile: AgentProfileRefV1Schema,
  depends_on: z.array(idSchema).max(64).default([]),
  input_artifact_ids: z.array(idSchema).max(128).default([]),
  allowed_tool_ids: z.array(idSchema).max(64).default([]),
  output_schema_digest: digestSchema,
  budget: AgentBudgetV1Schema,
  idempotency_key: z.string().min(8).max(128)
}).strict().superRefine((task, ctx) => {
  if (task.depends_on.includes(task.task_id)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["depends_on"], message: "A task cannot depend on itself" });
  }
  for (const key of ["depends_on", "input_artifact_ids", "allowed_tool_ids"] as const) {
    const values = task[key];
    if (new Set(values).size !== values.length) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: [key], message: "Values must be unique" });
    }
  }
});

export const AgentPlanV1Schema = z.object({
  schema_version: z.string().default("1"),
  plan_id: idSchema,
  mission_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  attempt_id: idSchema,
  source_commit: z.string().regex(/^[0-9a-f]{7,64}$/),
  policy_digest: digestSchema,
  registry_digest: digestSchema,
  tasks: z.array(AgentTaskV1Schema).min(1).max(64),
  max_parallel_tasks: z.number().int().min(1).max(16).default(1),
  compiler_version: z.string().min(1).max(64),
  created_at: timestampSchema
}).strict().superRefine((plan, ctx) => {
  const ids = plan.tasks.map((task) => task.task_id);
  if (new Set(ids).size !== ids.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tasks"], message: "Duplicate task IDs" });
    return;
  }
  const known = new Set(ids);
  plan.tasks.forEach((task, index) => {
    task.depends_on.forEach((dependency) => {
      if (!known.has(dependency)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tasks", index, "depends_on"], message: "Unknown dependency" });
      }
    });
  });
  const deps = new Map(plan.tasks.map((task) => [task.task_id, new Set(task.depends_on)]));
  const ready = [...deps.entries()].filter(([, values]) => values.size === 0).map(([id]) => id);
  let visited = 0;
  while (ready.length) {
    const current = ready.shift()!;
    visited += 1;
    for (const [id, values] of deps) {
      if (values.delete(current) && values.size === 0) ready.push(id);
    }
  }
  if (visited !== plan.tasks.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tasks"], message: "Task dependency cycle" });
  }
});

export const AgentFilesystemGrantV1Schema = z.object({
  root: AgentFilesystemRootSchema,
  access: AgentFilesystemAccessSchema
}).strict().superRefine((grant, ctx) => {
  if (grant.root === "source_snapshot" && grant.access === "write") {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["access"], message: "Source snapshot is read-only" });
  }
  if (grant.root === "artifacts" && grant.access === "read") {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["access"], message: "Artifacts are write-only in v1" });
  }
});

export const AgentCapabilityGrantV1Schema = z.object({
  schema_version: z.string().default("1"),
  grant_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  attempt_id: idSchema,
  sandbox_id: idSchema,
  task_id: idSchema,
  agent_id: idSchema,
  profile_digest: digestSchema,
  policy_digest: digestSchema,
  tool_registry_digest: digestSchema,
  tool_ids: z.array(idSchema).max(64).default([]),
  filesystem_grants: z.array(AgentFilesystemGrantV1Schema).max(8).default([]),
  network_policy_digest: digestSchema,
  budget: AgentBudgetV1Schema,
  nonce: idSchema,
  issued_at: timestampSchema,
  expires_at: timestampSchema,
  signature: z.string().max(1024).nullable().default(null)
}).strict().superRefine((grant, ctx) => {
  if (grant.expires_at <= grant.issued_at) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["expires_at"], message: "Grant must expire after issue time" });
  }
  if (new Set(grant.tool_ids).size !== grant.tool_ids.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tool_ids"], message: "Duplicate tool ID" });
  }
  const scopes = grant.filesystem_grants.map((item) => item.root + "|" + item.access);
  if (new Set(scopes).size !== scopes.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["filesystem_grants"], message: "Duplicate filesystem grant" });
  }
});

export const AgentActionEventV1Schema = z.object({
  schema_version: z.string().default("1"),
  event_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  attempt_id: idSchema,
  sandbox_id: idSchema,
  task_id: idSchema,
  agent_id: idSchema,
  profile_digest: digestSchema,
  sequence_number: z.number().int().min(1),
  action: AgentActionKindSchema,
  tool_id: idSchema.nullable().default(null),
  request_digest: digestSchema.nullable().default(null),
  output_digest: digestSchema.nullable().default(null),
  denial_code: idSchema.nullable().default(null),
  summary: z.string().min(1).max(500),
  occurred_at: timestampSchema
}).strict().superRefine((event, ctx) => {
  const isToolAction = ["proposed", "validated", "denied", "executed"].includes(event.action);
  if (isToolAction && (event.tool_id === null || event.request_digest === null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["tool_id"], message: "Tool action requires tool ID and request digest" });
  }
  if (event.action === "executed" && event.output_digest === null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["output_digest"], message: "Executed action requires output digest" });
  }
  if (event.action === "denied" && event.denial_code === null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["denial_code"], message: "Denied action requires denial code" });
  }
  if (event.action !== "denied" && event.denial_code !== null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["denial_code"], message: "Denial code is only valid for denied actions" });
  }
});

export const AgentExecutionRecordV1Schema = z.object({
  schema_version: z.string().default("1"),
  execution_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  attempt_id: idSchema,
  sandbox_id: idSchema,
  task_id: idSchema,
  agent_id: idSchema,
  profile_digest: digestSchema,
  runtime_bundle_digest: digestSchema,
  tool_registry_digest: digestSchema,
  model_manifest_digest: digestSchema.nullable().default(null),
  status: AgentExecutionStatusSchema,
  started_at: timestampSchema,
  finished_at: timestampSchema.nullable().default(null),
  inference_requests: z.number().int().min(0).default(0),
  input_tokens: z.number().int().min(0).default(0),
  output_tokens: z.number().int().min(0).default(0),
  tool_calls: z.number().int().min(0).default(0),
  denied_tool_calls: z.number().int().min(0).default(0),
  cpu_ms: z.number().int().min(0).default(0),
  peak_memory_mib: z.number().int().min(0).default(0),
  output_bytes: z.number().int().min(0).default(0),
  failure_code: idSchema.nullable().default(null)
}).strict().superRefine((record, ctx) => {
  if (record.status === "running" && (record.finished_at !== null || record.failure_code !== null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["finished_at"], message: "Running record cannot have terminal fields" });
  }
  if (record.status !== "running" && record.finished_at === null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["finished_at"], message: "Terminal record requires finished_at" });
  }
  if (record.finished_at !== null && record.finished_at < record.started_at) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["finished_at"], message: "Finished time precedes start time" });
  }
  if (record.status === "failed" && record.failure_code === null) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["failure_code"], message: "Failed record requires failure code" });
  }
});

export const AgentArtifactRefV1Schema = z.object({
  schema_version: z.string().default("1"),
  artifact_id: idSchema,
  organization_id: idSchema,
  project_id: idSchema,
  run_id: idSchema,
  attempt_id: idSchema,
  sandbox_id: idSchema,
  task_id: idSchema,
  kind: AgentArtifactKindSchema,
  media_type: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}\/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$/),
  size_bytes: z.number().int().min(0).max(1_073_741_824),
  sha256: digestSchema,
  evidence_artifact_id: idSchema,
  created_at: timestampSchema
}).strict();

export function validateAgentPlanAgainstMission(
  mission: z.infer<typeof AgenticMissionV1Schema>,
  plan: z.infer<typeof AgentPlanV1Schema>,
  registry: z.infer<typeof AgentProfileRegistryV1Schema>,
  verifiedRegistryDigest: string
): void {
  if (registry.organization_id !== mission.organization_id) {
    throw new Error("Profile registry belongs to another organization");
  }
  if (verifiedRegistryDigest !== mission.registry_digest || plan.registry_digest !== verifiedRegistryDigest) {
    throw new Error("Mission, plan, and verified registry digests do not match");
  }
  if (
    plan.mission_id !== mission.mission_id ||
    plan.organization_id !== mission.organization_id ||
    plan.project_id !== mission.project_id ||
    plan.run_id !== mission.run_id ||
    plan.source_commit !== mission.source_commit ||
    plan.policy_digest !== mission.policy_digest ||
    plan.registry_digest !== mission.registry_digest
  ) {
    throw new Error("Plan scope does not match the admitted mission");
  }
  const selected = new Set(mission.profiles.map((profile) =>
    profile.profile_id + "|" + profile.version + "|" + profile.profile_digest
  ));
  const revoked = new Set(registry.revoked_profile_digests);
  const registered = new Map(registry.profiles.map((profile) => [
    profile.profile_id + "|" + profile.version,
    profile
  ]));
  for (const task of plan.tasks) {
    const key = task.profile.profile_id + "|" + task.profile.version + "|" + task.profile.profile_digest;
    if (!selected.has(key)) throw new Error(`Task ${task.task_id} uses a profile not selected by the mission`);
    if (revoked.has(task.profile.profile_digest)) throw new Error(`Task ${task.task_id} profile has been revoked`);
    const profile = registered.get(task.profile.profile_id + "|" + task.profile.version);
    if (!profile) throw new Error(`Task ${task.task_id} profile is not registered`);
    if (profile.role !== task.role) throw new Error(`Task ${task.task_id} role does not match profile`);
    if (!profile.task_types.includes(task.task_type)) throw new Error(`Task ${task.task_id} type is not allowed`);
    if (profile.tool_ids.length < task.allowed_tool_ids.length ||
        task.allowed_tool_ids.some((id) => !profile.tool_ids.includes(id))) {
      throw new Error(`Task ${task.task_id} requests ungranted tools`);
    }
    const limits = task.budget;
    const granted = profile.budget;
    for (const key of Object.keys(granted) as (keyof typeof granted)[]) {
      if (limits[key] > granted[key]) throw new Error(`Task ${task.task_id} exceeds profile budget: ${key}`);
    }
  }
  if (plan.max_parallel_tasks > mission.budget.max_parallel_tasks) {
    throw new Error("Plan parallelism exceeds mission budget");
  }
}

export type AgenticRole = z.infer<typeof AgenticRoleSchema>;
export type AgentBudgetV1 = z.infer<typeof AgentBudgetV1Schema>;
export type AgentProfileRefV1 = z.infer<typeof AgentProfileRefV1Schema>;
export type AgentProfileV1 = z.infer<typeof AgentProfileV1Schema>;
export type AgentToolDefinitionV1 = z.infer<typeof AgentToolDefinitionV1Schema>;
export type AgentProfileRegistryV1 = z.infer<typeof AgentProfileRegistryV1Schema>;
export type AgenticMissionV1 = z.infer<typeof AgenticMissionV1Schema>;
export type AgentTaskV1 = z.infer<typeof AgentTaskV1Schema>;
export type AgentPlanV1 = z.infer<typeof AgentPlanV1Schema>;
export type AgentFilesystemGrantV1 = z.infer<typeof AgentFilesystemGrantV1Schema>;
export type AgentCapabilityGrantV1 = z.infer<typeof AgentCapabilityGrantV1Schema>;
export type AgentActionEventV1 = z.infer<typeof AgentActionEventV1Schema>;
export type AgentExecutionRecordV1 = z.infer<typeof AgentExecutionRecordV1Schema>;
export type AgentArtifactRefV1 = z.infer<typeof AgentArtifactRefV1Schema>;
