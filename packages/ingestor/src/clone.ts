import { z } from "zod";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import type { GitExec } from "./git";
import { headOf, treeShaOf } from "./git";

/**
 * Pinned clone: fetch the repository, then check out the EXACT commit SHA
 * resolved earlier. Afterwards verify HEAD == SHA — anything else is refusal.
 */
export interface CloneResult {
  workspacePath: string;
  commitSha: string;
  treeSha: string;
}

export async function clonePinned(
  git: GitExec,
  url: string,
  commitSha: string,
  destParent: string,
  sandboxId: string,
): Promise<CloneResult> {
  const workspacePath = path.join(destParent, sandboxId);
  await mkdir(destParent, { recursive: true });

  const init = await git(["clone", "--quiet", "--no-tags", "--filter=blob:none", url, workspacePath]);
  if (init.code !== 0) throw new Error(`git clone failed: ${init.stderr.trim()}`);

  const checkout = await git(["checkout", "--quiet", commitSha], { cwd: workspacePath });
  if (checkout.code !== 0) throw new Error(`git checkout ${commitSha} failed: ${checkout.stderr.trim()}`);

  const head = await headOf(git, workspacePath);
  if (head.toLowerCase() !== commitSha.toLowerCase()) {
    throw new Error(
      `clone verification failed: HEAD ${head} != pinned ${commitSha}`,
    );
  }
  const treeSha = await treeShaOf(git, workspacePath);
  return { workspacePath, commitSha: head, treeSha };
}

export const ProvenanceSchema = z.object({
  provider: z.enum(["github", "git"]),
  url: z.string().min(1),
  requestedRef: z.string().min(1),
  refName: z.string().min(1),
  commitSha: z.string().regex(/^[0-9a-f]{40}$/),
  treeSha: z.string().regex(/^[0-9a-f]{40}$/),
}).strict();
export type Provenance = z.infer<typeof ProvenanceSchema>;
