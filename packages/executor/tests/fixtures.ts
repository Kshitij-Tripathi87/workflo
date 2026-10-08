import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";

export function git(args: string[], cwd?: string): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile("git", args, { cwd }, (error, _stdout, stderr) => {
      if (error) reject(new Error(`git ${args.join(" ")}: ${stderr}`));
      else resolve();
    });
  });
}

export interface FixtureRemote {
  /** Path usable as a git remote URL (local). */
  url: string;
  dir: string;
  tag: string;
  cleanup: () => Promise<void>;
}

/** Create a REAL git repo with the given files, committed on main. */
export async function createFixtureRemote(
  files: Record<string, string>,
  label: string,
): Promise<FixtureRemote> {
  const root = await mkdtemp(path.join(tmpdir(), `wf-ingest-${label}-`));
  const dir = path.join(root, "src-repo");
  await mkdir(dir, { recursive: true });

  await git(["init", "-b", "main"], dir);
  await git(["config", "user.email", "fixture@workflo.test"], dir);
  await git(["config", "user.name", "Workflo Fixture"], dir);

  for (const [rel, content] of Object.entries(files)) {
    const filePath = path.join(dir, ...rel.split("/"));
    await mkdir(path.dirname(filePath), { recursive: true });
    await writeFile(filePath, content, "utf8");
  }
  await git(["add", "-A"], dir);
  await git(["-c", "commit.gpgsign=false", "commit", "-m", `${label} initial`], dir);

  const head: string = await new Promise((resolve, reject) => {
    execFile("git", ["rev-parse", "HEAD"], { cwd: dir }, (e, out) =>
      e ? reject(e) : resolve(out.trim()),
    );
  });

  return {
    url: dir.replace(/\\/g, "/"),
    dir,
    tag: head,
    cleanup: () => rm(root, { recursive: true, force: true }),
  };
}

export const NODE_FIXTURE_FILES: Record<string, string> = {
  "package.json": JSON.stringify(
    {
      name: "fixture-node-app",
      version: "0.0.1",
      type: "module",
      scripts: {
        start: "node src/server.js",
        test: "node --test tests",
      },
    },
    null,
    2,
  ),
  "src/server.js": `
import http from "node:http";
const port = Number(process.env.PORT || 48711);
const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  if (req.url === "/work") {
    const n = 21 * 2;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ answer: n }));
    return;
  }
  res.writeHead(404); res.end();
});
server.listen(port, "127.0.0.1");
process.on("SIGTERM", () => server.close(() => process.exit(0)));
`,
  "tests/server.test.js": `
import { test } from "node:test";
import assert from "node:assert";
import { spawn } from "node:child_process";

test("health endpoint returns ok", async () => {
  const proc = spawn(process.execPath, ["src/server.js"], {
    env: { ...process.env, PORT: "48713" },
    stdio: "ignore",
  });
  try {
    let body = null;
    for (let i = 0; i < 50; i++) {
      try {
        const res = await fetch("http://127.0.0.1:48713/health");
        body = await res.json();
        break;
      } catch { await new Promise((r) => setTimeout(r, 100)); }
    }
    assert.deepEqual(body, { ok: true });
  } finally {
    proc.kill("SIGTERM");
  }
});
`,
};

export const CRASH_FIXTURE_FILES: Record<string, string> = {
  "package.json": JSON.stringify({
    name: "fixture-crash-app", type: "module",
    scripts: { start: "node src/server.js", test: "node --test tests" },
  }),
  "src/server.js": `console.error("boom: cannot bind"); process.exit(3);`,
  "tests/x.test.js": `import { test } from "node:test"; test("noop", () => {});`,
};

export const HANG_FIXTURE_FILES: Record<string, string> = {
  "package.json": JSON.stringify({
    name: "fixture-hang-app", type: "module",
    scripts: { start: "node src/server.js", test: "node --test tests" },
  }),
  "src/server.js": `setInterval(() => {}, 1000); // listens on nothing, never ready`,
  "tests/x.test.js": `import { test } from "node:test"; test("noop", () => {});`,
};

export const TESTFAIL_FIXTURE_FILES: Record<string, string> = {
  "package.json": JSON.stringify({
    name: "fixture-testfail-app", type: "module",
    scripts: { start: "node src/server.js", test: "node --test tests" },
  }),
  "src/server.js": `
import http from "node:http";
const port = Number(process.env.PORT || 48715);
http.createServer((req, res) => {
  if (req.url === "/health") { res.writeHead(200); res.end("{\\"ok\\":true}"); return; }
  res.writeHead(404); res.end();
}).listen(port, "127.0.0.1");
process.on("SIGTERM", () => process.exit(0));
`,
  "tests/failing.test.js": `
import { test } from "node:test";
import assert from "node:assert";
test("deliberately failing", () => { assert.equal(1, 2); });
`,
};

export const CHILD_DAEMON_FIXTURE_FILES: Record<string, string> = {
  "package.json": JSON.stringify({
    name: "fixture-daemon-app", type: "module",
    scripts: { start: "node src/server.js", test: "node --test tests" },
  }),
  "src/server.js": `
import http from "node:http";
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const port = Number(process.env.PORT || 48717);
// Spawn a detached child that outlives naive kills.
const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { detached: true, stdio: "ignore" });
child.unref();
if (process.env.WORKFLO_CHILD_PID_FILE) writeFileSync(process.env.WORKFLO_CHILD_PID_FILE, String(child.pid));
http.createServer((req, res) => {
  if (req.url === "/health") { res.writeHead(200); res.end("{\\"ok\\":true}"); return; }
  res.writeHead(404); res.end();
}).listen(port, "127.0.0.1");
process.on("SIGTERM", () => process.exit(0));
`,
  "tests/x.test.js": `import { test } from "node:test"; test("noop", () => {});`,
};
