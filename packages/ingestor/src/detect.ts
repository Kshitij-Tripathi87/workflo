import { readFile, access } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

/**
 * Deterministic project detection — package.json / pyproject.toml answer the
 * question. The LLM is never asked to classify a project.
 */

export type ProjectType = "node" | "python" | "unknown";

export interface ProjectProfile {
  type: ProjectType;
  framework?: string | undefined;
  packageManager?: "npm" | "pnpm" | "yarn" | undefined;
  /** Exact dependency-install command lines (each = argv array). */
  install: string[][];
  testCommand?: string[] | undefined;
  startCommand?: string[] | undefined;
  /** Conventional port for the detected framework, if any. */
  port?: number | undefined;
}

const NODE_PACKAGE_JSON = z.object({
  scripts: z.record(z.string()).optional(),
  packageManager: z.string().optional(),
  dependencies: z.record(z.string()).optional(),
  devDependencies: z.record(z.string()).optional(),
}).passthrough();

async function exists(p: string): Promise<boolean> {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

function splitCommandLine(_cmd: string): string[] {
  // reserved for future shell-safe splitting; unused until then
  return [];
}
void splitCommandLine;

function detectPackageManager(pkg: { packageManager?: string }, locks: { pnpm: boolean; yarn: boolean; npm: boolean }): "npm" | "pnpm" | "yarn" {
  const declared = pkg.packageManager?.split("@")[0];
  if (declared === "npm" || declared === "pnpm" || declared === "yarn") return declared;
  if (locks.pnpm) return "pnpm";
  if (locks.yarn) return "yarn";
  return "npm";
}

export async function detectProject(workspacePath: string): Promise<ProjectProfile> {
  // --- Node -----------------------------------------------------------------
  const pkgPath = path.join(workspacePath, "package.json");
  if (await exists(pkgPath)) {
    const pkg = NODE_PACKAGE_JSON.parse(JSON.parse(await readFile(pkgPath, "utf8")));

    const locks = {
      pnpm: await exists(path.join(workspacePath, "pnpm-lock.yaml")),
      yarn: await exists(path.join(workspacePath, "yarn.lock")),
      npm: await exists(path.join(workspacePath, "package-lock.json")),
    };
    const pm = detectPackageManager(pkg as { packageManager?: string }, locks);
    const hasLock = locks.pnpm || locks.yarn || locks.npm;

    const deps = { ...pkg.dependencies, ...pkg.devDependencies };
    const depCount = Object.keys(deps ?? {}).filter((k) => (deps as Record<string, string>)[k]).length;

    const install: string[][] = [];
    if (depCount > 0) {
      if (pm === "pnpm") install.push(["pnpm", "install", "--frozen-lockfile"]);
      else if (pm === "yarn") install.push(["yarn", "install", "--frozen-lockfile"]);
      else install.push(hasLock ? ["npm", "ci"] : ["npm", "install", "--no-audit", "--no-fund"]);
    }

    const framework =
      deps && Object.keys(deps).find((d) => deps[d]) !== undefined
        ? ["next", "express", "fastify", "hono", "react", "vite"].find((d) => d in (deps ?? {}))
        : undefined;

    return {
      type: "node",
      ...(framework ? { framework } : {}),
      packageManager: pm,
      install,
      ...(pkg.scripts?.test ? { testCommand: [pm === "npm" ? "npm" : pm, "test"] } : {}),
      ...(pkg.scripts?.start ? { startCommand: [pm === "npm" ? "npm" : pm, "start"] } : {}),
      ...(framework === "next" ? { port: 3000 } : framework ? { port: 8080 } : {}),
    };
  }

  // --- Python ---------------------------------------------------------------
  const pyproject = path.join(workspacePath, "pyproject.toml");
  const requirements = path.join(workspacePath, "requirements.txt");
  const setupPy = path.join(workspacePath, "setup.py");
  if ((await exists(pyproject)) || (await exists(requirements)) || (await exists(setupPy))) {
    const install: string[][] = [["python", "-m", "venv", ".venv"]];
    const pip = process.platform === "win32" ? [".venv\\Scripts\\python", "-m", "pip"] : [".venv/bin/python", "-m", "pip"];
    if (await exists(requirements)) {
      install.push([...pip, "install", "-r", "requirements.txt"]);
    } else if (await exists(pyproject)) {
      install.push([...pip, "install", "."]);
    }
    const pyBin = process.platform === "win32" ? ".venv\\Scripts\\python" : ".venv/bin/python";
    return {
      type: "python",
      install,
      testCommand: [pyBin, "-m", "pytest"],
      // start command only if a conventional entrypoint exists
      ...((await exists(path.join(workspacePath, "app.py")))
        ? { startCommand: [pyBin, "app.py"] }
        : {}),
    };
  }

  return { type: "unknown", install: [] };
}
