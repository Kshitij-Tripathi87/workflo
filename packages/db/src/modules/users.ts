import type { TenantSession } from "../client";
import type { Db } from "../client";

/**
 * Class A (identity). Users are visible to themselves and to members of the
 * current tenant org. Creation runs without tenant context (signup path) and
 * must be called via db.system(...) by the auth service only.
 */

export interface UserRow {
  id: string;
  email: string;
  display_name: string;
  created_at: Date;
  last_login_at: Date | null;
}

export async function createUser(
  db: Db,
  email: string,
  displayName = "",
): Promise<UserRow> {
  return db.system(async (client) => {
    const { rows } = await client.query<UserRow>(
      `INSERT INTO users (email, display_name) VALUES ($1, $2)
       ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
       RETURNING *`,
      [email.toLowerCase(), displayName],
    );
    return rows[0]!;
  });
}

export async function getUserByEmail(db: Db, email: string): Promise<UserRow | null> {
  return db.system(async (client) => {
    const { rows } = await client.query<UserRow>(
      `SELECT * FROM users WHERE email = $1`,
      [email.toLowerCase()],
    );
    return rows[0] ?? null;
  });
}

export async function getUser(s: TenantSession, id: string): Promise<UserRow | null> {
  const { rows } = await s.query<UserRow>(`SELECT * FROM users WHERE id = $1`, [id]);
  return rows[0] ?? null;
}
