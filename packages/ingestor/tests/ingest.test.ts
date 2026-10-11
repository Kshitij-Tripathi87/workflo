import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { realGit, resolveRef } from "../src/git";
import { clonePinned } from "../src/clone";
import { ingest } from "../src/ingest";
import { detectProject } from "../src/detect";
import { createFixtureRemote, NODE_FIXTURE_FILES, git } from "./fixtures";

describe("ingestor against a real local git remote", () => {
  it("resolves main → immutable SHA, pins clone, verifies HEAD, detects node project", async () => {
    const remote = await createFixtureRemote(NODE_FIXTURE_FILES, "happy");
    const dest = await mkdtemp(path.join(tmpdir(), "wf-ingest-dest-"));
    try {
      const resolved = await resolveRef(realGit, remote.url, "main");
      expect(resolved.commitSha).toMatch(/^[0-9a-f]{40}$/);
      expect(resolved.refName).toBe("refs/heads/main");

      const cloned = await clonePinned(realGit, remote.url, resolved.commitSha, dest, "sbx-a1");
      expect(cloned.commitSha).toBe(resolved.commitSha);
      expect(cloned.treeSha).toMatch(/^[0-9a-f]{40}$/);

      const project = await detectProject(cloned.workspacePath);
      expect(project.type).toBe("node");
      expect(project.packageManager).toBe("npm");
      expect(project.testCommand).toEqual(["npm", "test"]);
      expect(project.startCommand).toEqual(["npm", "start"]);
      expect(project.install).toEqual([]); // deps-free fixture — no install phase
    } finally {
      await remote.cleanup();
      await rm(dest, { recursive: true, force: true });
    }
  });

  it("pins despite the branch moving after resolution", async () => {
    const remote = await createFixtureRemote(NODE_FIXTURE_FILES, "pinning");
    const dest = await mkdtemp(path.join(tmpdir(), "wf-ingest-dest-"));
    try {
      const resolved = await resolveRef(realGit, remote.url, "main");

      // Advance main by one commit AFTER resolving.
      await writeFile(path.join(remote.dir, "NEW.txt"), "drift");
      await git(["add", "NEW.txt"], remote.dir);
      await git(["-c", "commit.gpgsign=false", "commit", "-m", "drift"], remote.dir);
      const newHead = await resolveRef(realGit, remote.url, "main");
      expect(newHead.commitSha).not.toBe(resolved.commitSha);

      const cloned = await clonePinned(realGit, remote.url, resolved.commitSha, dest, "sbx-pin");
      expect(cloned.commitSha).toBe(resolved.commitSha); // the ORIGINAL sha
    } finally {
      await remote.cleanup();
      await rm(dest, { recursive: true, force: true });
    }
  });

  it("unknown ref fails loudly", async () => {
    const remote = await createFixtureRemote(NODE_FIXTURE_FILES, "badref");
    try {
      await expect(resolveRef(realGit, remote.url, "nonexistent-branch")).rejects.toThrow(
        /ref not found|ls-remote/,
      );
    } finally {
      await remote.cleanup();
    }
  });

  it("full ingest() returns provenance + profile through the schema", async () => {
    const remote = await createFixtureRemote(NODE_FIXTURE_FILES, "full");
    const dest = await mkdtemp(path.join(tmpdir(), "wf-ingest-dest-"));
    try {
      const repo = await ingest(
        { url: remote.url, ref: "main", destRoot: dest, sandboxId: "sbx-full" },
        realGit,
      );
      expect(repo.provider).toBe("git");
      expect(repo.requestedRef).toBe("main");
      expect(repo.commitSha).toMatch(/^[0-9a-f]{40}$/);
      expect(repo.project.type).toBe("node");
      expect(repo.workspacePath).toContain("sbx-full");
    } finally {
      await remote.cleanup();
      await rm(dest, { recursive: true, force: true });
    }
  });
});

describe("project detector", () => {
  it("python detection via pyproject.toml", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "wf-detect-py-"));
    await mkdir(path.join(dir), { recursive: true });
    try {
      await writeFile(path.join(dir, "pyproject.toml"), '[project]\nname = "x"\n', "utf8");
      await writeFile(path.join(dir, "requirements.txt"), "pytest\n", "utf8");
      const project = await detectProject(dir);
      expect(project.type).toBe("python");
      expect(project.install.length).toBeGreaterThan(0);
      expect(project.testCommand?.join(" ")).toContain("pytest");
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("unknown when no marker files exist", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "wf-detect-none-"));
    try {
      const project = await detectProject(dir);
      expect(project.type).toBe("unknown");
      expect(project.testCommand).toBeUndefined();
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("pnpm lockfile selects pnpm", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "wf-detect-pnpm-"));
    try {
      await writeFile(path.join(dir, "package.json"), JSON.stringify({
        name: "x",
        scripts: { test: "vitest run", start: "node index.js" },
        dependencies: { express: "^4.0.0" },
      }));
      await writeFile(path.join(dir, "pnpm-lock.yaml"), "lockfileVersion: '9.0'\n");
      const project = await detectProject(dir);
      expect(project.packageManager).toBe("pnpm");
      expect(project.install).toEqual([["pnpm", "install", "--frozen-lockfile"]]);
      expect(project.framework).toBe("express");
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
