import { describe, expect, it } from "vitest";
import { readdir, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Db, migrate } from "../src";
import { superDb, SUPER_URL } from "./helpers";

const migrationsDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "migrations",
);

describe("migrations", () => {
  it("applies cleanly from an empty database (globalSetup ran it)", async () => {
    const db = superDb();
    try {
      // Second application is a no-op.
      const applied = await migrate(db, migrationsDir);
      expect(applied).toEqual([]);

      const files = (await readdir(migrationsDir)).filter((f) => f.endsWith(".sql"));
      const { rows } = await db.system((c) =>
        c.query<{ name: string }>(
          "SELECT name FROM schema_migrations ORDER BY name",
        ),
      );
      expect(rows.map((r) => r.name)).toEqual(files.sort());
    } finally {
      await db.close();
    }
  });

  it("rejects re-applying a changed migration (checksum mismatch)", async () => {
    const db = superDb();
    try {
      await expect(
        db.system(async (c) => {
          await c.query(
            "UPDATE schema_migrations SET sha256 = 'tampered' WHERE name = '0001_init.sql'",
          );
        }),
      ).resolves.toBeUndefined();

      await expect(migrate(db, migrationsDir)).rejects.toThrow(
        /different checksum/,
      );

      // restore for other tests
      const sql = await readFile(path.join(migrationsDir, "0001_init.sql"), "utf8");
      const sha = createHash("sha256").update(sql).digest("hex");
      await db.system((c) =>
        c.query(
          "UPDATE schema_migrations SET sha256 = $1 WHERE name = '0001_init.sql'",
          [sha],
        ),
      );
    } finally {
      await db.close();
    }
  });

  it("all 12 domain tables exist with expected tenancy columns", async () => {
    const db = Db.fromUrl(SUPER_URL);
    try {
      const tables = [
        "organizations", "users", "memberships", "projects",
        "github_connections", "missions", "runs", "evidence_events",
        "findings", "receipts", "audit_logs", "inference_usage",
      ];
      const { rows } = await db.system((c) =>
        c.query<{ table_name: string }>(
          `SELECT table_name FROM information_schema.tables
           WHERE table_schema = 'public' AND table_name = ANY($1)
           ORDER BY table_name`,
          [tables],
        ),
      );
      expect(rows.map((r) => r.table_name).sort()).toEqual([...tables].sort());

      // organization_id present on every tenant-owned table
      const tenantTables = tables.filter(
        (t) => t !== "organizations" && t !== "users",
      );
      const { rows: cols } = await db.system((c) =>
        c.query<{ table_name: string }>(
          `SELECT table_name FROM information_schema.columns
           WHERE table_schema = 'public' AND column_name = 'organization_id'
             AND table_name = ANY($1)`,
          [tenantTables],
        ),
      );
      expect(cols.map((r) => r.table_name).sort()).toEqual([...tenantTables].sort());
    } finally {
      await db.close();
    }
  });

  it("RLS is enabled and forced on all tables", async () => {
    const db = superDb();
    try {
      const { rows } = await db.system((c) =>
        c.query<{ relname: string; relrowsecurity: boolean; relforcerowsecurity: boolean }>(
          `SELECT relname, relrowsecurity, relforcerowsecurity
           FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
           ORDER BY relname`,
        ),
      );
      for (const row of rows) {
        if (row.relname === "schema_migrations") continue;
        expect(row.relrowsecurity, `${row.relname} RLS`).toBe(true);
        expect(row.relforcerowsecurity, `${row.relname} FORCE RLS`).toBe(true);
      }
      expect(rows.length).toBeGreaterThanOrEqual(12);
    } finally {
      await db.close();
    }
  });
});
