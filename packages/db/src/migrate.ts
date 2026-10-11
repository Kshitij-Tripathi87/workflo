import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import type { Db } from "./client";

/**
 * Migrations must run as a superuser/owner (embedded dev or CI postgres),
 * NOT as workflo_app: DDL, roles, policies and grants require it.
 * Each .sql file manages its own transaction; the runner only tracks them.
 */
export async function migrate(db: Db, migrationsDir: string): Promise<string[]> {
  return db.system(async (client) => {
    await client.query(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        name       text PRIMARY KEY,
        sha256     text NOT NULL,
        applied_at timestamptz NOT NULL DEFAULT now()
      )
    `);

    const files = (await readdir(migrationsDir))
      .filter((f) => f.endsWith(".sql"))
      .sort();

    const applied: string[] = [];
    for (const file of files) {
      const sql = await readFile(path.join(migrationsDir, file), "utf8");
      const sha256 = createHash("sha256").update(sql).digest("hex");

      const existing = await client.query(
        "SELECT sha256 FROM schema_migrations WHERE name = $1",
        [file],
      );
      if (existing.rowCount) {
        const row = existing.rows[0] as { sha256: string };
        if (row.sha256 !== sha256) {
          throw new Error(
            `migration ${file} was already applied with a different checksum`,
          );
        }
        continue;
      }

      await client.query(sql);
      await client.query(
        "INSERT INTO schema_migrations (name, sha256) VALUES ($1, $2)",
        [file, sha256],
      );
      applied.push(file);
    }

    return applied;
  });
}
