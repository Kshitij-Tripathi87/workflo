import EmbeddedPostgres from "embedded-postgres";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const PG_PORT = 55632;
export const MIGRATIONS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "migrations",
);

export default async function setup() {
  const databaseDir = await mkdtemp(path.join(tmpdir(), "workflo-pg-"));

  const embedded = new EmbeddedPostgres({
    databaseDir,
    port: PG_PORT,
    user: "postgres",
    password: "postgres",
    persistent: false,
    initdbFlags: ["--encoding=UTF-8", "--locale=C"],
    onLog: () => undefined,
    onError: () => undefined,
  });

  await embedded.initialise();
  await embedded.start();

  const superClient = embedded.getPgClient();
  await superClient.connect();
  await superClient.query(`CREATE DATABASE workflo_test`);
  await superClient.end();

  // Run migrations as superuser so roles/policies/grants apply.
  const { Db } = await import("../src/client");
  const { migrate } = await import("../src/migrate");
  const db = Db.fromUrl(
    `postgres://postgres:postgres@127.0.0.1:${PG_PORT}/workflo_test`,
  );
  try {
    await migrate(db, MIGRATIONS_DIR);
  } finally {
    await db.close();
  }

  return async () => {
    await embedded.stop();
    await rm(databaseDir, { recursive: true, force: true });
  };
}
