import { z } from "zod";
import path from "node:path";

/**
 * Landlock ruleset loader/validator (ABI v3, Linux 5.13+).
 *
 * Landlock is applied by the in-namespace pre-exec helper
 * (workflo-landlock), not by this TypeScript code. This module validates the
 * declarative ruleset the helper consumes: everything not listed is denied.
 */

/**
 * A ruleset path is either absolute (/usr) or a ${workspace} template that is
 * substituted at provisioning time. No parent traversal, normalized only.
 */
const PathRef = z
  .string()
  .refine(
    (p) => {
      if (/^\$\{workspace\}(\/.*)?$/.test(p)) {
        const rest = p.replace(/^\$\{workspace\}/, "") || "/";
        return /^\/.*$/.test(rest) && !rest.includes("..") && path.posix.normalize(rest) === rest;
      }
      return /^\//.test(p) && !p.includes("..") && path.posix.normalize(p) === p;
    },
    { message: "landlock paths must be absolute or ${workspace}-relative templates" },
  );

export const LandlockRulesetSchema = z.object({
  name: z.string().regex(/^[a-z0-9][a-z0-9-]{0,63}$/),
  abi: z.literal(3),
  /** Read-only allowed paths (toolchain). */
  readOnly: z.array(PathRef).default([]),
  /** Read-write allowed paths (workspace, /tmp). */
  readWrite: z.array(PathRef).default([]),
}).strict();

export type LandlockRuleset = z.infer<typeof LandlockRulesetSchema>;

export function loadLandlockRuleset(rawJson: string): LandlockRuleset {
  return LandlockRulesetSchema.parse(JSON.parse(rawJson));
}

export interface LandlockInstantiated {
  readOnly: string[];
  readWrite: string[];
}

/** Substitute ${workspace} with the actual sandbox workspace mount. */
export function instantiateRuleset(
  ruleset: LandlockRuleset,
  vars: { workspace: string },
): LandlockInstantiated {
  const sub = (p: string) =>
    p.replace(/\$\{workspace\}/g, vars.workspace);
  return {
    readOnly: ruleset.readOnly.map(sub),
    readWrite: ruleset.readWrite.map(sub),
  };
}
