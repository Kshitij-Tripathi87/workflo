import { readFile } from "node:fs/promises";
import path from "node:path";

/**
 * Attestation records — what the sandbox PROVES happened, structurally
 * aligned with ReceiptV4Schema.sandbox.* (isolation_attestation,
 * teardown_proof, canary_check). The receipt (Day 8) embeds these.
 */

export interface IsolationAttestation {
  sandboxId: string;
  runtime: "bwrap";
  namespaces: {
    user: boolean;
    pid: boolean;
    net: boolean;
    uts: boolean;
    ipc: boolean;
    mount: boolean;
  };
  networkPolicy: "deny" | "allow-loopback";
  usernsRoot: boolean;
  cgroup: {
    path: string;
    cpuMax: string;
    memoryMaxBytes: string;
    pidsMax: string;
    limitsVerified: boolean;
    mismatches: string[];
  };
  seccomp: {
    profile: string;
    attached: boolean;
  };
  landlock: {
    ruleset: string;
    attached: boolean;
  };
  startedAt: string;
}

export interface CanaryCheck {
  ranAt: string;
  command: string[];
  expected: "fail";
  exitCode: number | null;
  /** true = egress was blocked as required (command failed). */
  succeeded: boolean;
}

export interface TeardownProof {
  sandboxId: string;
  endedAt: string;
  checks: {
    processesGone: boolean;
    cgroupGone: boolean;
    netnsGone: boolean;
    workspaceRemoved: boolean;
  };
  /** true only when every check passed. */
  verified: boolean;
}

export async function loadPolicyFile(
  policiesRoot: string,
  kind: "seccomp" | "landlock",
  name: string,
): Promise<string> {
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(name)) {
    throw new Error(`invalid ${kind} policy name: ${name}`);
  }
  return readFile(path.join(policiesRoot, kind, `${name}.json`), "utf8");
}
