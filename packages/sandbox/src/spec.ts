import { z } from "zod";

/**
 * SandboxSpec — the declarative request for a sealed execution environment.
 *
 * Implemented with real Linux primitives:
 *   bubblewrap (user/pid/net/mount/uts/ipc namespaces)
 *   + cgroups v2 (cpu/memory/pids)
 *   + seccomp profile (syscall allowlist)
 *   + Landlock (filesystem access rules)
 *
 * Docker is NEVER the security boundary.
 */

export const ResourceLimitsSchema = z.object({
  /** CPU cores (fractional allowed). 2 = "200000 100000" for cpu.max. */
  cpu: z.number().positive().max(64),
  memoryMb: z.number().int().positive().max(512 * 1024),
  pids: z.number().int().positive().max(65535),
  /** Hard wall-clock cap; the supervisor kills and fails the run past this. */
  timeoutSec: z.number().int().positive().max(6 * 3600),
}).strict();

export const NetworkPolicySchema = z.enum(["deny", "allow-loopback"]);

export const SandboxSpecSchema = z.object({
  /** Stable identifier for cgroup/netns/teardown bookkeeping. */
  sandboxId: z.string().regex(/^[a-z0-9][a-z0-9-]{2,62}$/),
  runId: z.string().uuid(),

  /** Host path of the pre-populated isolated workspace (wiped on teardown). */
  workspaceDir: z.string().min(1),
  /** Where the workspace appears inside the sandbox. */
  workspaceMount: z.string().regex(/^\/[a-zA-Z0-9\-._/]*$/).default("/workspace"),
  /** Cwd inside the sandbox. */
  workingDir: z.string().regex(/^\//).default("/workspace"),

  /** Host dirs mounted READ-ONLY (toolchain: /usr, /lib, /lib64, /bin...). */
  roBinds: z.array(z.string().min(1)).default([]),

  /** Complete environment for the workload (host env is cleared). */
  env: z.record(z.string()).default({}),

  network: NetworkPolicySchema.default("deny"),
  resources: ResourceLimitsSchema,

  /** Map current uid/gid to root in the user namespace (default true). */
  usernsRoot: z.boolean().default(true),

  /** Seccomp profile name under infra/policies/seccomp/. */
  seccompProfile: z.string().default("default"),
  /** Landlock ruleset name under infra/policies/landlock/. */
  landlockRuleset: z.string().default("base"),
}).strict();

export type ResourceLimits = z.infer<typeof ResourceLimitsSchema>;
export type NetworkPolicy = z.infer<typeof NetworkPolicySchema>;
export type SandboxSpec = z.infer<typeof SandboxSpecSchema>;

export function parseSandboxSpec(input: unknown): SandboxSpec {
  return SandboxSpecSchema.parse(input);
}
