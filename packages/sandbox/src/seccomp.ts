import { z } from "zod";

/**
 * Seccomp profile loader/validator (libseccomp JSON subset).
 *
 * The loader VALIDATES and REPRESENTS the policy. Compilation to a BPF
 * program happens in a Linux build step (scmp_bpf) — this package never
 * pretends to compile BPF in TypeScript.
 */

const ACTIONS = [
  "SCMP_ACT_KILL",
  "SCMP_ACT_KILL_PROCESS",
  "SCMP_ACT_ERRNO",
  "SCMP_ACT_TRAP",
  "SCMP_ACT_ALLOW",
  "SCMP_ACT_LOG",
  "SCMP_ACT_NOTIFY",
] as const;

const SyscallRuleSchema = z.object({
  names: z.array(z.string().regex(/^[a-z0-9_]+$/)).min(1),
  action: z.enum(ACTIONS),
  errnoRet: z.number().int().min(0).max(4095).optional(),
}).strict();

export const SeccompProfileSchema = z.object({
  defaultAction: z.enum(ACTIONS),
  defaultErrnoRet: z.number().int().min(0).max(4095).optional(),
  architectures: z.array(z.string().regex(/^SCMP_ARCH_/)).min(1),
  syscalls: z.array(SyscallRuleSchema).min(1),
  flags: z.array(z.string()).optional(),
  /** Documentation-in-band: rationale for the profile. */
  comment: z.string().max(2000).optional(),
}).strict();

export type SeccompProfile = z.infer<typeof SeccompProfileSchema>;

/** Dangerous syscalls that must never appear under SCMP_ACT_ALLOW. */
const FORBIDDEN_ALLOW = new Set([
  "ptrace", "mount", "umount", "umount2", "pivot_root", "chroot",
  "kexec_load", "kexec_file_load", "init_module", "finit_module",
  "delete_module", "bpf", "perf_event_open", "userfaultfd",
  "io_uring_setup", "io_uring_enter", "keyctl", "add_key", "request_key",
  "acct", "swapon", "swapoff", "reboot", "sethostname", "setdomainname",
  "move_mount", "open_tree", "fsopen", "fsmount", "fsconfig", "quotactl",
  "lookup_dcookie", "nfsservctl", "vhangup",
]);

export interface SeccompAudit {
  profileName: string;
  defaultAction: string;
  syscallCount: number;
  forbiddenInAllow: string[];
  warnings: string[];
}

export function loadSeccompProfile(name: string, rawJson: string): SeccompProfile {
  return SeccompProfileSchema.parse(JSON.parse(rawJson));
}

export function auditSeccompProfile(profileName: string, profile: SeccompProfile): SeccompAudit {
  const forbiddenInAllow: string[] = [];
  const warnings: string[] = [];
  let syscallCount = 0;

  for (const rule of profile.syscalls) {
    syscallCount += rule.names.length;
    if (rule.action === "SCMP_ACT_ALLOW") {
      for (const name of rule.names) {
        if (FORBIDDEN_ALLOW.has(name)) forbiddenInAllow.push(name);
      }
    }
  }

  if (profile.defaultAction === "SCMP_ACT_ALLOW") {
    warnings.push("default action ALLOW — not a deny-default profile");
  }
  if (!profile.architectures.length) {
    warnings.push("no architectures listed");
  }

  return { profileName, defaultAction: profile.defaultAction, syscallCount, forbiddenInAllow, warnings };
}
