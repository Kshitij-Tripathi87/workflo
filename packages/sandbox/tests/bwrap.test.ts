import { describe, expect, it } from "vitest";
import { buildBwrapArgv } from "../src/bwrap";
import { makeSpec } from "./helpers";

describe("bwrap argv builder", () => {
  it("produces the sealed-sandbox flag set", () => {
    const plan = buildBwrapArgv({
      spec: makeSpec({
        roBinds: ["/usr"],
        env: { CI: "true" },
      }),
      command: ["npm", "test"],
    });

    const argv = plan.argv.join(" ");
    expect(argv).toContain("--unshare-all");
    expect(argv).toContain("--die-with-parent");
    expect(argv).toContain("--new-session");
    expect(argv).toContain("--clearenv");
    expect(argv).toContain("--setenv CI true");
    expect(argv).toContain("--hostname wf-sbx-sbx-test01");
    expect(argv).toContain("--uid 0");
    expect(argv).toContain("--ro-bind /usr /usr");
    expect(argv).toContain("--bind /var/lib/workflo/sandboxes/sbx-test01 /workspace");
    expect(argv).toContain("--chdir /workspace");
    expect(plan.argv.at(-3)).toBe("--");
    expect(plan.argv.at(-2)).toBe("npm");
    expect(plan.argv.at(-1)).toBe("test");
  });

  it("empty command is rejected", () => {
    expect(() =>
      buildBwrapArgv({ spec: makeSpec(), command: [] }),
    ).toThrow(/empty/);
  });

  it("seccomp fd token + landlock helper wrapping work", () => {
    const plan = buildBwrapArgv({
      spec: makeSpec(),
      command: ["node", "test.js"],
      seccompProgramPath: "/var/lib/workflo/seccomp/default.bpf",
      landlockHelperPath: "/usr/local/bin/workflo-landlock",
      landlockRulesetPath: "/etc/workflo/landlock/base.json",
    });
    expect(plan.seccompFdPath).toBe("/var/lib/workflo/seccomp/default.bpf");
    expect(plan.argv).toContain("--seccomp");
    const sep = plan.argv.indexOf("--");
    expect(plan.argv[sep + 1]).toBe("/usr/local/bin/workflo-landlock");
    expect(plan.argv.slice(sep + 3)).toEqual(["--", "node", "test.js"]);
  });

  it("network deny adds no caps; allow-loopback is documented + scoped", () => {
    const deny = buildBwrapArgv({ spec: makeSpec({ network: "deny" }), command: ["true"] });
    expect(deny.argv).not.toContain("--cap-add");

    const lo = buildBwrapArgv({
      spec: makeSpec({ network: "allow-loopback" }),
      command: ["true"],
    });
    expect(lo.argv.join(" ")).toContain("CAP_NET_ADMIN");
    expect(lo.notes.join(" ")).toContain("userns");
  });

  it("host env never leaks: only declared env after --clearenv", () => {
    const plan = buildBwrapArgv({
      spec: makeSpec({ env: { TOKEN: "xyz", PATH: "/usr/bin" } }),
      command: ["true"],
    });
    const clIdx = plan.argv.indexOf("--clearenv");
    expect(clIdx).toBeGreaterThan(-1);
    const setenvs: string[] = [];
    for (let i = 0; i < plan.argv.length; i++) {
      if (plan.argv[i] === "--setenv") setenvs.push(`${plan.argv[i + 1]}=${plan.argv[i + 2]}`);
    }
    expect(setenvs.sort()).toEqual(["PATH=/usr/bin", "TOKEN=xyz"]);
  });
});
