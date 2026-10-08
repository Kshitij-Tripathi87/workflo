import type { SandboxSpec } from "./spec";

/**
 * bwrap argv builder — pure. Security-critical flags are non-negotiable:
 *
 *   --unshare-all        user+pid+net+uts+ipc+mount namespaces
 *   --die-with-parent    workload cannot outlive the supervisor
 *   --new-session        no controlling tty / session escape
 *   --clearenv           host environment never leaks
 *
 * Network "deny" is enforced by the private net namespace (loopback only,
 * all egress blocked). Landlock is applied by an in-namespace pre-exec helper
 * (workflo-landlock) when present; seccomp attaches via --seccomp fd when a
 * compiled profile binary is available (Linux build step).
 */

export interface BwrapPlan {
  argv: string[];
  /** Extra env for the launcher itself (never the workload). */
  seccompFdPath?: string;
  notes: string[];
}

export interface BwrapOptions {
  spec: SandboxSpec;
  command: string[];
  /** Absolute path to a compiled seccomp BPF program (optional). */
  seccompProgramPath?: string;
  /** Absolute path to the landlock pre-exec helper (optional). */
  landlockHelperPath?: string;
  /** Landlock ruleset file to pass to the helper. */
  landlockRulesetPath?: string;
}

const SANDBOX_HOSTNAME_PREFIX = "wf-sbx-";

export function buildBwrapArgv(opts: BwrapOptions): BwrapPlan {
  const { spec, command } = opts;
  if (command.length === 0) throw new Error("sandboxed command is empty");

  const argv: string[] = ["bwrap"];
  const notes: string[] = [];

  argv.push("--unshare-all", "--die-with-parent", "--new-session");

  // Identity inside the sandbox.
  argv.push("--hostname", `${SANDBOX_HOSTNAME_PREFIX}${spec.sandboxId}`);
  if (spec.usernsRoot) {
    argv.push("--uid", "0", "--gid", "0");
  }

  // Filesystem: minimal root, read-only toolchain, writable workspace + /tmp.
  argv.push("--ro-bind", "/", "/");
  for (const bind of spec.roBinds) {
    argv.push("--ro-bind", bind, bind);
  }
  argv.push("--proc", "/proc");
  argv.push("--tmpfs", "/tmp");
  argv.push("--bind", spec.workspaceDir, spec.workspaceMount);
  argv.push("--chdir", spec.workingDir);

  // Environment: cleared, then exactly the declared env.
  argv.push("--clearenv");
  for (const [key, value] of Object.entries(spec.env)) {
    argv.push("--setenv", key, value);
  }

  // Network: namespaces do the isolation; nothing else to add here.
  // private net ns via --unshare-all; loopback stays down unless allowed.
  if (spec.network === "allow-loopback") {
    argv.push("--cap-add", "CAP_NET_ADMIN");
    notes.push("loopback enabled: CAP_NET_ADMIN inside userns only");
  }

  // seccomp: attach compiled BPF via fd when available.
  let seccompFdPath: string | undefined;
  if (opts.seccompProgramPath) {
    // bwrap reads the BPF program from the given fd; the launcher opens the
    // file and passes the fd number in place of the path token below.
    argv.push("--seccomp", "@FD@");
    seccompFdPath = opts.seccompProgramPath;
  } else {
    notes.push("seccomp profile not attached (no compiled program)");
  }

  // Landlock: helper runs first inside the namespace, then execs the workload.
  let inner = command;
  if (opts.landlockHelperPath && opts.landlockRulesetPath) {
    inner = [opts.landlockHelperPath, opts.landlockRulesetPath, "--", ...command];
  } else {
    notes.push("landlock helper not attached");
  }

  argv.push("--", ...inner);
  return { argv, ...(seccompFdPath !== undefined ? { seccompFdPath } : {}), notes };
}
