/**
 * Network namespace + nftables policy plans.
 *
 * Default Workflo posture is `deny`: the workload runs in a private netns
 * with loopback down — there is no default route, no interface, no egress.
 * A canary probe OUTSIDE the workload verifies this after provisioning.
 *
 * This module also provides the explicit netns plan used when an allow-listed
 * egress mode is introduced later (veth pair + default-deny nft + explicit
 * allow rules). Today only "deny" and "allow-loopback" are spec-legal.
 */

export interface NetnsPlan {
  name: string;
  create: string[][];
  destroy: string[][];
  verify: string[][];
  nftRuleset: string;
}

export function buildNetnsPlan(sandboxId: string): NetnsPlan {
  const name = `wf-${sandboxId}`;
  return {
    name,
    create: [
      ["ip", "netns", "add", name],
      ["ip", "netns", "exec", name, "nft", "-f", "-"],
    ],
    destroy: [["ip", "netns", "del", name]],
    verify: [["ip", "netns", "list"]],
    nftRuleset: defaultDenyNft(),
  };
}

/** Default-deny nftables ruleset: loopback only, everything else dropped. */
export function defaultDenyNft(): string {
  return [
    "table inet workflo_deny {",
    "  chain input {",
    "    type filter hook input priority 0; policy drop;",
    "    iif \"lo\" accept",
    "  }",
    "  chain output {",
    "    type filter hook output priority 0; policy drop;",
    "    oif \"lo\" accept",
    "  }",
    "  chain forward {",
    "    type filter hook forward priority 0; policy drop;",
    "  }",
    "}",
    "",
  ].join("\n");
}

/** Whether a netns listing output contains this namespace name. */
export function netnsPresent(listOutput: string, name: string): boolean {
  return listOutput
    .split("\n")
    .map((line) => line.trim().split(/\s+/)[0])
    .some((n) => n === name);
}
