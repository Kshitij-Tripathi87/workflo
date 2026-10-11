import EmbeddedPostgres from "embedded-postgres";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const PG_PORT = 55634;

const migrationsDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "db",
  "migrations",
);

export default async function setup() {
  const databaseDir = await mkdtemp(path.join(tmpdir(), "workflo-exec-pg-"));
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
  await superClient.query(`CREATE DATABASE workflo_executor_test`);
  await superClient.end();

  const { Db } = await import("@workflo/db");
  const { migrate } = await import("@workflo/db");
  const db = Db.fromUrl(
    `postgres://postgres:postgres@127.0.0.1:${PG_PORT}/workflo_executor_test`,
  );
  try {
    await migrate(db, migrationsDir);
  } finally {
    await db.close();
  }

  return async () => {
    await embedded.stop();
    await rm(databaseDir, { recursive: true, force: true });
  };
}
