# API Contract — `v1`

This is the **frozen** contract for the Workflo REST API. Anything in
`packages/workflo-schema/src/workflo_schema/api.py` is the source of
truth; this document is the human-readable companion.

## Versioning

- **Backwards-compatible additions** (new optional fields): no version bump.
- **Anything else** (rename, removal, type change, new required field):
  bump the version and add a migration entry.

Current version: **`v1`** (matches `/v1/` URL prefix).

---

## Authentication

Two authentication methods are supported:

### 1. API Key (for CI / automation)

Every request must include an API key header:

```http
POST /v1/runs HTTP/1.1
X-API-Key: wfl_<32-hex-chars>
Content-Type: application/json
```

Missing or invalid → `401 Unauthorized`. The key is hashed (SHA-256) on
the server; the plaintext key is **never** stored or logged.

For the demo, a seeded key can be issued by `POST /v1/auth/demo-token`.

### 2. OAuth 2.0 Device Authorization Grant (RFC 8628) — for CLI users

The CLI uses the device flow for human authentication. The flow:

1. CLI calls `POST /v1/auth/device/code` with `client_id` and optional `scope`
2. Server returns `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in`, `interval`
3. CLI opens `verification_uri_complete` in browser (or prints `user_code` + `verification_uri` for headless)
4. User visits the URL, enters `user_code`, approves/denies
5. CLI polls `POST /v1/auth/device/token` with `device_code` until authorized
6. Server returns `access_token`, `refresh_token`, `expires_in`, `scope`
7. CLI uses `access_token` as `X-API-Key` for subsequent requests
8. When `access_token` expires, CLI calls `POST /v1/auth/token/refresh` with `refresh_token`
9. On logout, CLI calls `POST /v1/auth/token/revoke`

Supported clients: `workflo_cli`, `astra_cli`, `nexus_cli` (each with product-specific scopes).

---

## Endpoints

### `POST /v1/runs`

Queue a new run. Returns the initial `RunStatus` (status: `queued`);
the actual execution happens in a background task.

**Request body** (`RunRequest`):

```json
{
  "repo_url": "https://github.com/example/my-saas-app.git",
  "probe_groups": ["test", "security"],
  "commit_sha": "a1b2c3d4e5f6",
  "config": {
    "timeout_seconds": 300,
    "memory_mb": 2048
  }
}
```

**With `web`** — `start_command` and `port` are **required** when
`"web"` is in `probe_groups`:

```json
{
  "repo_url": "https://github.com/example/my-saas-app.git",
  "probe_groups": ["web", "security"],
  "start_command": "python app.py",
  "port": 5000
}
```

**Validation failures** return `400 Bad Request` with a structured body:

```json
{
  "detail": "probe_groups includes 'web' but missing required fields: start_command, port. Either provide them on the request, or add them to a workflo.yaml in the target repo's root. Failing fast before container creation."
}
```

**Successful response** (`200 OK`, body is a `RunStatus`):

```json
{
  "run_id": "7f3a2b8c-1234-5678-9abc-def012345678",
  "status": "queued",
  "created_at": "2026-08-21T16:42:11.123456Z",
  "receipt": null,
  "error": null
}
```

### `GET /v1/runs/{run_id}`

Poll for the latest status of a run. Returns a `RunStatus`.

**When status == "completed"**:

```json
{
  "run_id": "7f3a2b8c-1234-5678-9abc-def012345678",
  "status": "completed",
  "created_at": "2026-08-21T16:42:11.123456Z",
  "receipt": {},
  "error": null
}
```

**When status == "failed"** (infrastructure crash, not test failure):

```json
{
  "run_id": "7f3a2b8c-1234-5678-9abc-def012345678",
  "status": "failed",
  "created_at": "2026-08-21T16:42:11.123456Z",
  "receipt": null,
  "error": "Ollama did not respond within 30s; receipt not produced."
}
```

### `POST /v1/auth/demo-token`

Demo-only. Returns a fixed, seeded API key for the demo account.

```json
{ "api_key": "wfl_abc123def456" }
```

---

### `POST /v1/auth/device/code`

Request a device authorization code (RFC 8628 Section 3.1).

**Request** (`application/x-www-form-urlencoded`):
```
client_id=workflo_cli&scope=openid profile offline_access workflo:runs:create
```

**Response** (`200 OK`):
```json
{
  "device_code": "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://auth.cortex.dev/device",
  "verification_uri_complete": "https://auth.cortex.dev/device?user_code=WDJB-MJHT",
  "expires_in": 1800,
  "interval": 5
}
```

**Errors**: `400 Bad Request` for invalid `client_id` or `scope`.

---

### `POST /v1/auth/device/token`

Poll for access token (RFC 8628 Section 3.4).

**Request** (`application/x-www-form-urlencoded`):
```
grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS&client_id=workflo_cli
```

**Success response** (`200 OK`):
```json
{
  "access_token": "wfl_at_...",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "wfl_rt_...",
  "scope": "openid profile offline_access workflo:runs:create workflo:runs:read workflo:receipts:read workflo:projects:read"
}
```

**Error responses** (`400 Bad Request` with error body):
- `authorization_pending` — user hasn't approved yet (retry after `interval`)
- `slow_down` — polling too fast (increase interval)
- `access_denied` — user denied authorization
- `expired_token` — device code expired
- `invalid_grant` — invalid or already-used device code

---

### `POST /v1/auth/token/refresh`

Refresh an access token (RFC 6749 Section 6).

**Request** (`application/x-www-form-urlencoded`):
```
grant_type=refresh_token&refresh_token=wfl_rt_...&client_id=workflo_cli
```

**Response** (`200 OK`) — same shape as device token response. Refresh tokens are rotated.

---

### `POST /v1/auth/token/revoke`

Revoke a token (RFC 7009).

**Request** (`application/x-www-form-urlencoded`):
```
token=wfl_rt_...&token_type_hint=refresh_token&client_id=workflo_cli
```

**Response** (`200 OK`):
```json
{ "revoked": true }
```

Always returns 200 per RFC 7009, even if token not found.

---

### `POST /v1/auth/keys/provision`

Register an Ed25519 public key for receipt signing. The private key stays
on the device; only the public key is registered. Once provisioned, the
key's `key_id` can be embedded in receipts to enable provenance verification
(third parties can fetch the public key from this directory to verify
both the signature AND that the key belongs to a known, authenticated
device/user/org).

**Requires:** `Authorization: Bearer <access_token>` (device-flow session).

**Request**:
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA...\n-----END PUBLIC KEY-----",
  "device_id": "alice-laptop-2026"
}
```

**Response** (`200 OK`):
```json
{
  "key_id": "9f3b2c1a-...",
  "fingerprint": "abc123def456...",
  "device_id": "alice-laptop-2026",
  "provisioned_at": "2026-08-17T10:30:00Z"
}
```

**Errors:**
- `400` — invalid PEM or non-Ed25519 key
- `401` — missing/invalid Bearer token
- `409` — key already provisioned by a different device, or previously revoked

**Idempotent:** provisioning the same `(public_key, device_id)` twice returns
the same `key_id`.

---

### `GET /v1/auth/keys/{key_id}`

Fetch public key info by `key_id`. **Public endpoint** — no auth needed,
so third-party verifiers can check signatures and key status.

**Response** (`200 OK`):
```json
{
  "key_id": "9f3b2c1a-...",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...",
  "fingerprint": "abc123def456...",
  "device_id": "alice-laptop-2026",
  "user_id": "user-abc",
  "organization_id": "org-xyz",
  "provisioned_at": "2026-08-17T10:30:00Z",
  "revoked_at": null,
  "status": "active"
}
```

**Errors:** `404` — unknown `key_id`.

---

### `POST /v1/auth/keys/{key_id}/revoke`

Revoke a provisioned key. Only the user who provisioned the key can
revoke it. Revoked keys remain in the directory for audit but are marked
`status: "revoked"` and rejected by verifiers.

**Requires:** `Authorization: Bearer <access_token>`.

**Response** (`200 OK`):
```json
{
  "key_id": "9f3b2c1a-...",
  "revoked": true,
  "revoked_at": "2026-08-20T14:00:00Z"
}
```

**Errors:**
- `401` — missing/invalid Bearer token
- `403` — token doesn't match the key's `user_id`
- `404` — unknown `key_id`

---

## Field reference

### `RunRequest`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `repo_url` | string | yes | git URL (https, git@, ssh, file:// for dev) |
| `probe_groups` | list of strings | yes | at least one functional tier |
| `commit_sha` | string | no | pinned commit, ≤ 64 chars |
| `start_command` | string | when `web` in `probe_groups` | shell-free command for app under test |
| `port` | int | when `web` in `probe_groups` | 1..65535 |
| `config` | object | no | optional overrides (see below) |

**`probe_groups` vocabulary** (case-sensitive):

- `test` — surface tier: the repo's native pytest + smoke
- `deep-test` — deep tier: + LLM-generated probes (requires the `-deep` worker image)
- `aggressive-test` — deep + future chaos/fuzz layer
- `web` — Playwright-driven browser probes (requires the `-web` worker image)
- `security` — composable with any functional tier; adds tenant-isolation probes

**`config` recognized keys** (unknown keys are ignored, not rejected):

| Key | Type | Range | Default |
|-----|------|-------|---------|
| `timeout_seconds` | int | 10..3600 | 600 |
| `memory_mb` | int | 256..16384 | 2048 |
| `cpu_cores` | float | 0.5..8.0 | 2.0 |

### `RunStatus`

See endpoint examples above.

---

## CLI parity

`workflo run --via-api <base_url> ...` round-trips through this exact
contract. The CLI constructs a `RunRequest`, POSTs to `/v1/runs`, then
polls `GET /v1/runs/{run_id}`. Receipts produced via the API are
byte-identical (modulo timestamps/run IDs) to those produced by a local
CLI run against the same repo/commit.

---

## Known limitations (deferred)

- In-memory run store (`_runs` dict). Survives process restarts? No.
  TODO: swap to Postgres before production.
- No Redis-backed queue. Single-process execution only. Horizontal worker
  scaling requires a queue.
- Device flow uses a fixed demo user (`demo-user`) and default project.
  Real user accounts and org/workspace selection need to be implemented.
- No pagination on `GET /v1/runs` (it's currently per-id only).
