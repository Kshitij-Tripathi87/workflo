/**
 * Explicit sandbox environment policy.
 *
 * The workload gets a constructed environment — never `process.env` verbatim.
 * Deny-list wins over allow-list; anything unknown is dropped.
 */

const ALLOW_EXACT = new Set([
  "PATH", "HOME", "LANG", "TMPDIR", "TMP", "TEMP", "PORT", "HOSTNAME",
  "USER", "LOGNAME", "PWD", "CI", "SHELL", "TERM", "TZ",
  "NODE_ENV", "PYTHONUNBUFFERED", "PIP_DISABLE_PIP_VERSION_CHECK",
]);

const ALLOW_PREFIXES = ["WORKFLO_", "LC_"];

const DENY_PATTERNS: RegExp[] = [
  /^AWS_/i, /^GITHUB_/i, /^GH_/i, /^GIT_/i, /^OPENAI/i, /^ANTHROPIC/i,
  /^AZURE_/i, /^GOOGLE_/i, /^GCLOUD/i, /^KUBERNETES/i, /^DOCKER_/i,
  /^SSH_/i, /^PG/i, /^MYSQL/i, /^DATABASE/i, /^DB_/i,
  /^REDIS/i, /^STRIPE/i, /^TWILIO/i, /^SENTRY/i, /^NPM_CONFIG_TOKEN$/i,
  /(_|\b)(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIALS?)$/i,
];

export function isAllowedEnvKey(key: string): boolean {
  if (DENY_PATTERNS.some((p) => p.test(key))) return false;
  if (ALLOW_EXACT.has(key)) return true;
  return ALLOW_PREFIXES.some((p) => key.startsWith(p));
}

/**
 * Build the workload environment from a controlled base + explicitly
 * approved extras. Unknown host variables are dropped by construction.
 */
export function buildSandboxEnv(opts: {
  base?: Record<string, string | undefined>;
  extra?: Record<string, string>;
}): Record<string, string> {
  const out: Record<string, string> = {};
  const source = { ...(opts.base ?? {}), ...(opts.extra ?? {}) };
  for (const [key, value] of Object.entries(source)) {
    if (value === undefined) continue;
    if (isAllowedEnvKey(key)) out[key] = value;
  }
  if (!out.PATH) out.PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
  if (!out.HOME) out.HOME = "/tmp";
  return out;
}
