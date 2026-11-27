import { describe, expect, it } from "vitest";
import {
  AgentActionEventV1Schema,
  AgentActionKindSchema,
  AgentBudgetV1Schema,
  AgentCapabilityGrantV1Schema,
  AgenticMissionV1Schema,
  AgenticRoleSchema,
  AgentPlanV1Schema,
  AgentProfileV1Schema
} from "../src/agentic";

const digest = (hex: string) => "sha256:" + hex.repeat(64);
const createdAt = "2026-11-21T08:00:00.000Z";

describe("agentic contract mirror", () => {
  it("keeps the role and action vocabularies explicit", () => {
    expect(AgenticRoleSchema.options).toEqual([
      "mission_supervisor", "ingestor", "executor", "explorer", "test_designer",
      "browser_probe", "security_probe", "judge", "notary"
    ]);
    expect(AgentActionKindSchema.options).toEqual([
      "proposed", "validated", "denied", "executed", "observed"
    ]);
  });

  it("rejects unbounded inference and unsafe profile entrypoints", () => {
    expect(AgentBudgetV1Schema.safeParse({
      max_tokens: 0, max_inference_requests: 1
    }).success).toBe(false);
    expect(AgentProfileV1Schema.safeParse({
      profile_id: "explorer", version: "1.0.0", role: "explorer",
      runtime_bundle_digest: digest("a"), entrypoint: "../escape.py",
      task_types: ["repository_qa"], input_schema_digest: digest("b"),
      output_schema_digest: digest("c"), tool_ids: [],
      delegatable_roles: [], model_profile_id: null, model_artifact_digests: [],
      budget: {}, created_by: { user_id: "user_1", organization_id: "org_1" },
      created_at: createdAt
    }).success).toBe(false);
  });

  it("rejects tenant-mismatched missions and strict unknown fields", () => {
    const parsed = AgenticMissionV1Schema.safeParse({
      mission_id: "mission_1", organization_id: "org_1", project_id: "project_1",
      run_id: "run_1", source_commit: "abcdef0", policy_digest: digest("a"),
      registry_digest: digest("b"), task_type: "repository_qa",
      objective: "Check this repository for regressions.",
      profiles: [{ profile_id: "explorer", version: "1.0.0", profile_digest: digest("c") }],
      budget: {}, idempotency_key: "mission-idem-0001",
      created_by: { user_id: "user_1", organization_id: "org_other" },
      created_at: createdAt, untrusted_override: true
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects cyclic or self-referential task DAGs", () => {
    const profile = {
      profile_id: "explorer", version: "1.0.0", profile_digest: digest("a")
    };
    const task = {
      task_id: "task_1", task_type: "repository_qa", role: "explorer",
      profile, depends_on: ["task_1"], input_artifact_ids: [],
      allowed_tool_ids: [], output_schema_digest: digest("b"),
      budget: {}, idempotency_key: "task-idem-0001"
    };
    expect(AgentPlanV1Schema.safeParse({
      plan_id: "plan_1", mission_id: "mission_1", organization_id: "org_1",
      project_id: "project_1", run_id: "run_1", attempt_id: "attempt_1",
      source_commit: "abcdef0", policy_digest: digest("c"),
      registry_digest: digest("d"), tasks: [task], compiler_version: "1.0.0",
      created_at: createdAt
    }).success).toBe(false);
  });

  it("rejects expired capability grants and incomplete action evidence", () => {
    const grant = AgentCapabilityGrantV1Schema.safeParse({
      grant_id: "grant_1", organization_id: "org_1", project_id: "project_1",
      run_id: "run_1", attempt_id: "attempt_1", sandbox_id: "sandbox_1",
      task_id: "task_1", agent_id: "agent_1", profile_digest: digest("a"),
      policy_digest: digest("b"), tool_registry_digest: digest("c"),
      tool_ids: [], filesystem_grants: [], network_policy_digest: digest("d"),
      budget: {}, nonce: "nonce_1", issued_at: createdAt,
      expires_at: createdAt
    });
    expect(grant.success).toBe(false);

    expect(AgentActionEventV1Schema.safeParse({
      event_id: "event_1", organization_id: "org_1", project_id: "project_1",
      run_id: "run_1", attempt_id: "attempt_1", sandbox_id: "sandbox_1",
      task_id: "task_1", agent_id: "agent_1", profile_digest: digest("a"),
      sequence_number: 1, action: "denied", tool_id: "repo.read",
      request_digest: digest("b"), summary: "Tool was denied.", occurred_at: createdAt
    }).success).toBe(false);
  });
});
