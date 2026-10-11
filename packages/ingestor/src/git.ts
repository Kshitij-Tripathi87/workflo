import { execFile } from "node:child_process";

/** Minimal git execution seam (injectable for tests). */
export type GitExec = (
  args: string[],
  opts?: { cwd?: string; timeoutMs?: number },
) => Promise<{ code: number; stdout: string; stderr: string }>;

export const realGit: GitExec = (args, opts) =>
  new Promise((resolve, reject) => {
    execFile(
      "git",
      args,
      { cwd: opts?.cwd, timeout: opts?.timeoutMs ?? 60_000, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout, stderr) => {
        const code = error && typeof error.code === "number" ? error.code : error ? 1 : 0;
        resolve({ code, stdout: String(stdout), stderr: String(stderr) });
      },
    );
  });

const SHA_RE = /^[0-9a-f]{7,64}$/;

/** Parse repo coordinates. Accepts HTTPS/SSH GitHub URLs and local paths. */
export function parseRepoUrl(input: string): {
  provider: "github" | "git";
  url: string;
  owner?: string;
  repo?: string;
} {
  const trimmed = input.trim();
  const https = trimmed.match(
    /^https?:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?(\/.*)?$/,
  );
  if (https?.[1] && https[2]) {
    return {
      provider: "github",
      url: `https://github.com/${https[1]}/${https[2]}.git`,
      owner: https[1],
      repo: https[2],
    };
  }
  const ssh = trimmed.match(/^git@github\.com:([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?$/);
  if (ssh?.[1] && ssh[2]) {
    return {
      provider: "github",
      url: `git@github.com:${ssh[1]}/${ssh[2]}.git`,
      owner: ssh[1],
      repo: ssh[2],
    };
  }
  if (/^https?:\/\//.test(trimmed) || trimmed.startsWith("git@")) {
    return { provider: "git", url: trimmed };
  }
  // Local path / file URL (fixtures, mounted mirrors).
  return { provider: "git", url: trimmed.replace(/\\/g, "/") };
}

/**
 * Resolve a ref (branch, tag, partial SHA) to an immutable full commit SHA
 * via `git ls-remote`. Never trust a symbolic ref downstream.
 */
export async function resolveRef(
  git: GitExec,
  url: string,
  ref: string,
): Promise<{ requestedRef: string; commitSha: string; refName: string }> {
  // Full SHA given — pass through, but verify the server has it later at clone.
  if (/^[0-9a-f]{40}$/.test(ref)) {
    return { requestedRef: ref, commitSha: ref, refName: ref };
  }

  const result = await git(["ls-remote", url, ref, `${ref}/*`, `refs/${ref}`, `refs/${ref}/*`]);
  if (result.code !== 0) {
    throw new Error(`git ls-remote failed for ${ref}: ${result.stderr.trim()}`);
  }
  const lines = result.stdout.split("\n").filter((l) => l.trim().length > 0);
  if (lines.length === 0) throw new Error(`ref not found: ${ref}`);

  // Prefer exact match (heads/tags), then peeled annotated tag (^{}).
  const entries = lines.map((l) => {
    const [sha, name] = l.trim().split(/\s+/);
    return { sha: sha ?? "", name: name ?? "" };
  });
  const exact =
    entries.find((e) => e.name === `refs/heads/${ref}`) ??
    entries.find((e) => e.name === `refs/tags/${ref}^{}`) ??
    entries.find((e) => e.name === `refs/tags/${ref}`) ??
    entries.find((e) => e.name === ref) ??
    entries.find((e) => e.name.endsWith(`/${ref}`));
  const picked = exact ?? entries[0]!;
  if (!SHA_RE.test(picked.sha)) {
    throw new Error(`ls-remote returned unparseable line: ${lines[0]}`);
  }
  return { requestedRef: ref, commitSha: picked.sha, refName: picked.name };
}

/** Return `git rev-parse HEAD` for a checkout (post-clone verification). */
export async function headOf(git: GitExec, cwd: string): Promise<string> {
  const result = await git(["rev-parse", "HEAD"], { cwd });
  if (result.code !== 0) throw new Error(`rev-parse HEAD failed: ${result.stderr.trim()}`);
  return result.stdout.trim();
}

/** Tree digest for provenance (receipt tree_digest). */
export async function treeShaOf(git: GitExec, cwd: string): Promise<string> {
  const result = await git(["rev-parse", "HEAD^{tree}"], { cwd });
  if (result.code !== 0) throw new Error(`rev-parse tree failed: ${result.stderr.trim()}`);
  return result.stdout.trim();
}
