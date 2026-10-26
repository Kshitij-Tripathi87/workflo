import mysql, { type Pool } from "mysql2/promise";

let pool: Pool | null = null;

export class TrialSignupInputError extends Error {
  constructor(message = "Enter a valid work email address.") {
    super(message);
    this.name = "TrialSignupInputError";
  }
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
type TrialSignupExecutor = Pick<Pool, "execute">;

export function normalizeTrialEmail(value: unknown) {
  if (typeof value !== "string") throw new TrialSignupInputError();
  const email = value.trim().toLowerCase();
  if (email.length > 320 || !EMAIL_PATTERN.test(email)) throw new TrialSignupInputError();
  return email;
}

export function requireTrialConsent(value: unknown) {
  if (value !== true) throw new TrialSignupInputError("Please confirm consent before requesting a trial.");
}

export async function persistTrialSignup(value: unknown, consent: unknown, executor: TrialSignupExecutor, source = "landing_hero") {
  const email = normalizeTrialEmail(value);
  requireTrialConsent(consent);
  await executor.execute(
    `INSERT INTO trial_signups (email, source, consentedAt)
     VALUES (?, ?, CURRENT_TIMESTAMP)
     ON DUPLICATE KEY UPDATE updatedAt = CURRENT_TIMESTAMP, consentedAt = CURRENT_TIMESTAMP`,
    [email, source],
  );
  return { email };
}

function getPool() {
  if (!process.env.DATABASE_URL) throw new Error("Trial signup storage is unavailable.");
  if (!pool) pool = mysql.createPool(process.env.DATABASE_URL);
  return pool;
}

export async function createTrialSignup(value: unknown, consent: unknown, source = "landing_hero") {
  return persistTrialSignup(value, consent, getPool(), source);
}
