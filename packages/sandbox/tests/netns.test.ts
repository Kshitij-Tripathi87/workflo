import { describe, expect, it } from "vitest";
import { buildNetnsPlan, defaultDenyNft, netnsPresent } from "../src/netns";

describe("netns + nftables", () => {
  it("plan is named wf-<sandboxId> with create/destroy/verify", () => {
    const plan = buildNetnsPlan("sbx-test01");
    expect(plan.name).toBe("wf-sbx-test01");
    expect(plan.create[0]).toEqual(["ip", "netns", "add", "wf-sbx-test01"]);
    expect(plan.destroy[0]).toEqual(["ip", "netns", "del", "wf-sbx-test01"]);
    expect(plan.verify[0]).toEqual(["ip", "netns", "list"]);
  });

  it("nft ruleset is default-drop with loopback-only accept", () => {
    const nft = defaultDenyNft();
    expect(nft).toContain("policy drop");
    expect(nft.match(/policy drop/g)!.length).toBe(3); // input, output, forward
    expect(nft).toContain('iif "lo" accept');
    expect(nft).toContain('oif "lo" accept');
  });

  it("netnsPresent parses `ip netns list` output", () => {
    expect(netnsPresent("wf-a\nwf-b (id: 3)\n", "wf-b")).toBe(true);
    expect(netnsPresent("wf-a\n", "wf-nope")).toBe(false);
  });
});
