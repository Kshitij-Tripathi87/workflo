import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { loadSeccompProfile, auditSeccompProfile } from "../src/seccomp";
import { loadLandlockRuleset, instantiateRuleset } from "../src/landlock";
import { POLICIES_ROOT } from "./helpers";

describe("seccomp profiles (shipped under infra/policies)", () => {
  it("default.json loads, is deny-default, allows no forbidden syscall", async () => {
    const raw = await readFile(path.join(POLICIES_ROOT, "seccomp", "default.json"), "utf8");
    const profile = loadSeccompProfile("default", raw);
    const audit = auditSeccompProfile("default", profile);
    expect(profile.defaultAction).toBe("SCMP_ACT_ERRNO");
    expect(audit.forbiddenInAllow).toEqual([]);
    expect(audit.syscallCount).toBeGreaterThan(50);
    expect(profile.architectures).toContain("SCMP_ARCH_X86_64");
  });

  it("strict.json forbids execve/clone (single-command sandbox)", async () => {
    const raw = await readFile(path.join(POLICIES_ROOT, "seccomp", "strict.json"), "utf8");
    const profile = loadSeccompProfile("strict", raw);
    const allowed = profile.syscalls.flatMap((r) => (r.action === "SCMP_ACT_ALLOW" ? r.names : []));
    expect(allowed).not.toContain("execve");
    expect(allowed).not.toContain("execveat");
    expect(allowed).not.toContain("clone");
    expect(allowed).not.toContain("socket");
  });

  it("a profile allowing ptrace is rejected by audit", () => {
    const bad = loadSeccompProfile("bad", JSON.stringify({
      defaultAction: "SCMP_ACT_ERRNO",
      architectures: ["SCMP_ARCH_X86_64"],
      syscalls: [{ names: ["read", "ptrace"], action: "SCMP_ACT_ALLOW" }],
    }));
    const audit = auditSeccompProfile("bad", bad);
    expect(audit.forbiddenInAllow).toEqual(["ptrace"]);
  });

  it("default-ALLOW profiles are flagged", () => {
    const open = loadSeccompProfile("open", JSON.stringify({
      defaultAction: "SCMP_ACT_ALLOW",
      architectures: ["SCMP_ARCH_X86_64"],
      syscalls: [{ names: ["read"], action: "SCMP_ACT_ALLOW" }],
    }));
    const audit = auditSeccompProfile("open", open);
    expect(audit.warnings.join(" ")).toMatch(/deny-default/);
  });

  it("malformed profiles are rejected by the schema", () => {
    expect(() => loadSeccompProfile("x", '{"defaultAction":"BOGUS"}')).toThrow();
    expect(() => loadSeccompProfile("x", "not json")).toThrow();
  });
});

describe("landlock ruleset", () => {
  it("base.json loads and instantiates workspace substitution", async () => {
    const raw = await readFile(path.join(POLICIES_ROOT, "landlock", "base.json"), "utf8");
    const ruleset = loadLandlockRuleset(raw);
    const inst = instantiateRuleset(ruleset, { workspace: "/workspace" });
    expect(inst.readWrite).toContain("/workspace");
    expect(inst.readWrite).toContain("/tmp");
    expect(inst.readOnly).toContain("/usr");
    expect(inst.readWrite).not.toContain("${workspace}");
  });

  it("rejects relative / traversal / non-normalized paths", () => {
    for (const bad of ["etc/passwd", "/a/../b", "/a//b"]) {
      expect(() =>
        loadLandlockRuleset(
          JSON.stringify({ name: "t", abi: 3, readOnly: [bad], readWrite: [] }),
        ),
      ).toThrow();
    }
  });

  it("rejects abi versions other than 3", () => {
    expect(() =>
      loadLandlockRuleset('{"name":"t","abi":2,"readOnly":[],"readWrite":[]}'),
    ).toThrow();
  });
});
