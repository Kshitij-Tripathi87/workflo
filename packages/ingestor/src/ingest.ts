import { z } from "zod";
import { realGit, parseRepoUrl, resolveRef, type GitExec } from "./git";
import { clonePinned, ProvenanceSchema, type Provenance } from "./clone";
import { detectProject, type ProjectProfile } from "./detect";

/**
 * Ingestor: repo URL + ref → immutable provenance + prepared workspace +
 * deterministic project profile. Deterministic only — no LLM inference here.
 */

export interface IngestRequest {
  url: string;
  ref: string;
  /** Parent dir under which the workspace <destRoot>/<sandboxId> is created. */
  destRoot: string;
  sandboxId: string;
}

export type IngestedRepository = Provenance & {
  workspacePath: string;
  project: ProjectProfile;
};

export const IngestedRepositorySchema = ProvenanceSchema.extend({
  workspacePath: z.string().min(1),
  project: z.object({
    type: z.enum(["node", "python", "unknown"]),
    framework: z.string().optional(),
    packageManager: z.enum(["npm", "pnpm", "yarn"]).optional(),
    install: z.array(z.array(z.string())),
    testCommand: z.array(z.string()).optional(),
    startCommand: z.array(z.string()).optional(),
    port: z.number().int().positive().optional(),
  }).strict(),
}).strict();

export async function ingest(
  req: IngestRequest,
  git: GitExec = realGit,
): Promise<IngestedRepository> {
  const parsed = parseRepoUrl(req.url);
  const resolved = await resolveRef(git, parsed.url, req.ref);
  const cloned = await clonePinned(git, parsed.url, resolved.commitSha, req.destRoot, req.sandboxId);
  const project = await detectProject(cloned.workspacePath);

  return IngestedRepositorySchema.parse({
    provider: parsed.provider,
    url: parsed.url,
    requestedRef: resolved.requestedRef,
    refName: resolved.refName,
    commitSha: cloned.commitSha,
    treeSha: cloned.treeSha,
    workspacePath: cloned.workspacePath,
    project,
  });
}
