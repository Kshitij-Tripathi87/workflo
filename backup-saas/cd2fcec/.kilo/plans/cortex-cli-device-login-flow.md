# Cortex CLI Device Login Flow Plan

## Overview

This plan implements the OAuth 2.0 Device Authorization Grant (RFC 8628) for the Cortex CLI, enabling passwordless browser-based authentication for locally installed CLIs. The flow follows the pattern used by GitHub CLI, GitLab CLI, and other modern developer tools.

**Important**: This plan does NOT implement the Cortex website (cortex.dev). The website will be provided later. This plan covers only the CLI device login flow implementation.

## 1. User Experience

### Installation
```bash
npm install -g @cortex/workflo
# or
npm install -g @cortex/astra
# or
npm install -g @cortex/nexus
```

### Login Flow (with browser)
```bash
workflo login
```

**CLI output:**
```
To authenticate Workflo:

1. Open https://app.cortex.dev/device
2. Enter code: R7KM-L2QP

Waiting for browser approval...
```

**Optional browser auto-detection:**
```
Open browser? [Y/n]
```
If user accepts (or defaults), CLI opens the URL automatically.

### User Steps (after reaching the verification URL)
1. Opens `https://app.cortex.dev/device` in browser
2. Signs in to Cortex account
3. Completes MFA if enabled
4. Selects organization (e.g., "Cortex Labs")
5. Selects workspace (e.g., "Workflo Engineering")
6. Reviews requested permissions
7. Clicks "Approve device"

### CLI Detection & Completion
```
Authenticated successfully.
Organization: Cortex Labs
Workspace: Workflo Engineering
User: aarav@example.com
```

### Login Flow (no browser -- headless)
```bash
workflo login --no-browser
```

**CLI output:**
```
To authenticate Workflo:

1. Open https://app.cortex.dev/device
2. Enter code: R7KM-L2QP

Waiting for browser approval...
```
User completes authorization on a different device. CLI polls until approved or expired.

### Session Persistence
After successful login, the CLI stores credentials in the OS credential store. Subsequent runs use stored tokens without re-authentication.

```bash
workflo auth status
```
Outputs masked info about the active session.

### Logout
```bash
workflo logout
```
Revokes stored credentials, clears the OS credential store, and resets the active profile.

## 2. Complete Protocol Flow

```text
CLI
 │
 │ 1. Request device code
 ▼
Cortex Authorization Server
 │
 │ 2. Return device_code,
 │    user_code, verification_uri
 ▼
CLI displays code
 │
 │ 3. User opens browser
 ▼
Cortex browser login
 │
 │ 4. User authenticates
 │
 │ 5. User selects organization/workspace
 │
 │ 6. User approves requested scopes
 ▼
Authorization Server
 │
 │ 7. CLI polls token endpoint
 ▼
Access and refresh tokens
```

**Key properties:**
- CLI never receives user's password
- Tokens received only after browser authorization completes
- Device code is private to the CLI session
- User code is safe to display in terminal

## 3. Device Authorization Endpoints

Use a dedicated authorization service at `auth.cortex.dev` or similar base URL:

```
POST /oauth/device/authorize    # Step 1: Request device code
POST /oauth/token                # Step 3: Poll for tokens
GET  /oauth/userinfo             # Step optional: Get user info
POST /oauth/revoke               # Revoke tokens
```

### Step 1: Device Authorization Request

**CLI sends:**
```http
POST /oauth/device/authorize
Content-Type: application/x-www-form-urlencoded
cache-control: no-cache

client_id=workflo_cli
scope=openid profile offline_access workflo:runs:create workflo:runs:read
```

**Authorization Server Response:**
```json
{
  "device_code": "dc_7f91...",
  "user_code": "R7KM-L2QP",
  "verification_uri": "https://app.cortex.dev/device",
  "verification_uri_complete": "https://app.cortex.dev/device?user_code=R7KM-L2QP",
  "expires_in": 600,       // 10 minutes - device code lifetime
  "interval": 5            // polling interval in seconds
}
```

**Critical rules:**
- `device_code` is private to the CLI - NEVER display in terminal
- `user_code` is safe to display to user
- `expires_in` defines how long the device code remains valid
- `interval` defines minimum polling seconds (RFC 8628 recommends 5 seconds)

### Step 2: Browser Authorization

**User visits:**
```
https://app.cortex.dev/device
```

**Page displays:**
```
R7KM-L2QP

Workflo CLI wants access to:

- View your Cortex identity
- Access the selected Workflo workspace
- Start Workflo runs
- Read Workflo receipts

Organization: Cortex Labs
Workspace: Workflo Engineering

[Cancel] [Approve]
```

**User selects:**
- Organization from available list (only organizations where user is a member)
- Workspace from available list (only workspaces under selected organization)
- Clicks "Approve device"

**Authorization Server records:**
```text
device_code → user_id
device_code → organization_id
device_code → workspace_id
approved scopes
```

## 4. Step 3: CLI Polling

**CLI polls token endpoint:**
```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code
&device_code=dc_7f91...
&client_id=workflo_cli
```

### Before Approval
```json
{
  "error": "authorization_pending"
}
```

**CLI behavior:**
- Waits for server-provided polling interval (default 5 seconds)
- Maximum wait: `expires_in` (10 minutes by default)
- If user approves within window, proceeds to token response
- If interval elapses without approval, sends next poll

### After Approval
```json
{
  "access_token": "at_...",
  "refresh_token": "rt_...",
  "token_type": "Bearer",
  "expires_in": 900,      // 15 minutes
  "scope": "openid profile workflo:runs:create workflo:runs:read"
}
```

**Slow down mechanism:**
- Authorization server returns `slow_down` if CLI polls too frequently
- CLI must then increase wait time between polls
- RFC 8628 defines this to prevent API hammering

## 5. Token Design

### Access Token (short-lived)
```
Lifetime: approximately 15 minutes
Usage: API requests via Authorization header
```

**Used for:**
```http
Authorization: Bearer at_...
```

**Token payload identifies:**
```json
{
  "sub": "user_123",           // user identifier
  "client_id": "workflo_cli",  // CLI identifier
  "organization_id": "org_456",// selected organization
  "workspace_id": "ws_789",    // selected workspace
  "product": "workflo",        // product context
  "scopes": [                  // granted scopes
    "workflo:runs:create",
    "workflo:runs:read"
  ]
}
```

**Important:** Do NOT rely only on token claims for authorization. The API must still verify:
- Token is valid (signed, not expired)
- Token is not revoked
- User is still a member of the organization
- Organization is still active
- Workspace still exists
- User still has the required permission
- Resource belongs to the same organization

Membership/role changes should take effect before access token naturally expires when possible.

### Refresh Token (rotating, revocable, device-specific)
```
- Rotating: Each use invalidates previous refresh token
- Revocable: Can be revoked via API or logout
- Device-specific: Bound to the device that obtained it
- Stored securely: In OS credential store, never in plain config files
```

**Use case:** When access token expires, CLI uses refresh token to get new access token without user interaction.

## 6. Local Token Storage

### macOS
```text
Use macOS Keychain
```
- Item class: Generic Password or Internet Password
- Account: user_code or sub
- Value: refresh_token
- Service: "cortex-cli" + product name

### Windows
```text
Use Windows Credential Manager
```
- Credential type: Generic Credential
- Attribute: Cortex CLI refresh token

### Linux
```text
Prefer: Secret Service / GNOME Keyring / KDE Wallet
```
- Uses `secret-service` D-Bus API or respective wallet
- Falls back to `pass` command if available

### Fallback (no secure store)
```text
Store in ~/.config/cortex/credentials.json only with explicit warning
```
- File permissions: `0600` (owner read/write only)
- Must include warning banner on every CLI startup

### Never store tokens in:
- Shell history (`~/.bash_history`, `~/.zsh_history`)
- Plain project files
- Environment files committed to Git
- Console output / print statements
- npm configuration (`~/.npmrc`)
- Global logs or temp files

### Example Local Profile (metadata only, not secrets)
```text
~/.config/cortex/config.toml
```
```toml
active_organization = "org_456"
active_workspace = "ws_789"
```
**Note:** This file stores IDs only. Secrets (refresh tokens) must remain in the secure credential store. The profile can be committed to Git or shared; it does not contain secrets.

## 7. Multiple Accounts and Organizations

### Named Profiles
```bash
workflo login --profile personal
workflo login --profile cortex-labs
workflo auth list
workflo auth switch cortex-labs
```

**Example output:**
```
Profiles:
  personal       aarav@gmail.com       Personal Sandbox
* cortex-labs    aarav@cortex.dev      Cortex Labs
```

### Refresh Token Association
```text
Each refresh token is associated with:
- user
- client (CLI type)
- device (specific machine/instance)
- profile (named profile identity)
```

### Separate Organization/Workspace Selection
```bash
workflo org list
workflo org use cortex-labs
workflo workspace list
workflo workspace use engineering
```

**Rationale:** Prevents user who belongs to multiple organizations from accidentally running commands in the wrong tenant.

### Profile Switching Effect
When switching profiles, the CLI:
1. Revokes previous refresh token
2. Clears stored credentials from OS credential store
3. Loads new profile's credentials
4. Re-verifies organization/workspace membership

## 8. CLI Command Design

### Common Structure Across Products

#### Workflo
```bash
workflo login                    # Device login (OAuth 2.0)
workflo logout                   # Revoke credentials
workflo auth status              # Show active session
workflo org list                 # List accessible organizations
workflo org use cortex-labs      # Select organization
workflo workspace list           # List workspaces in org
workflo workspace use engineering# Select workspace
workflo run --repo <url> --test --security  # Run tests
```

#### ASTRA
```bash
astra login                      # Device login
astra auth status                # Show active session
astra org use cortex-labs        # Select organization
astra workspace use lunar-program# Select workspace
astra mission run mission.yaml   # Run mission design
```

#### Nexus
```bash
nexus login                      # Device login
nexus auth status                # Show active session
nexus org use acme               # Select organization
nexus workspace use supply-chain # Select workspace
nexus data sync                  # Sync operational data
nexus simulation run disruption.yaml  # Run simulation
```

**All products use the same Cortex identity service** but request product-specific scopes.

## 9. Scopes and Permissions

### Do Not Give Unlimited Access

### Workflo Scopes
```text
openid          # OpenID Connect identification
profile         # User profile (name, email)
workflo:runs:create  # Create/test execution runs
workflo:runs:read    # Read run results and reports
workflo:receipts:read  # Read cryptographic receipts
workflo:projects:read  # Read project configuration
```

### ASTRA Scopes
```text
openid          # OpenID Connect identification
profile         # User profile
astra:missions:create  # Create mission designs
astra:missions:read    # Read mission designs
astra:runs:create    # Run mission optimization
astra:reports:read   # Read mission reports
```

### Nexus Scopes
```text
openid          # OpenID Connect identification
profile         # User profile
nexus:data:read    # Read operational data
nexus:simulation:create  # Create simulations
nexus:decisions:read   # Read decisions
nexus:approvals:write  # Write approvals
```

### Execution Scopes (strictly separate)
```text
nexus:execution:propose   # Propose actions (agents only)
nexus:execution:approve   # Approve actions (human-only)
nexus:execution:execute   # Execute actions (highly restricted)
```

**Critical:** A CLI should never receive `nexus:execution:execute` merely because the user can view a Nexus workspace. Execution scopes require additional vetting.

### Scope Hierarchy
- **Read scopes**: View data, runs, receipts
- **Create scopes**: Create runs, missions, simulations
- **Execution scopes**: Propose → Approve → Execute (separate levels)
- **Admin scopes**: Full control (only for organization admins)

## 10. Device Security

### Device Code Properties
```text
- Short-lived: Expires after expires_in (10 minutes recommended)
- Single-use: Cannot be reused after first successful redemption
- Bound to client: Tied to specific client_id (workflo_cli, astra_cli, etc.)
- Bound to login attempt: One device code per login session
- Rate-limited: Maximum polls per interval
- Invalidated after approval: Becomes unusable after successful token exchange
- Invalidated after expiry: Expires after expires_in regardless of use
- Invalidated after too many failed attempts: Rate limiting on user_code entries
```

### Recommended Behavior
```text
Device code lifetime: 10 minutes
Polling interval: 5 seconds
Maximum polling duration: 10 minutes (equals expires_in)
User code attempts: Limited (e.g., 3 attempts before requiring new device code)
```

### Verification Page Context
```text
Application: Workflo CLI
Requested by: Workflo installation on device
Permissions: Run tests and read receipts

This CLI will be allowed to start Workflo runs in:
Cortex Labs / Engineering

[Cancel] [Approve]
```

### Higher-Risk Operations
For operations beyond basic test execution (e.g., Nexus execution:execute), require explicit confirmation in the browser with clear risk communication.

## 11. Headless Environments

### Environments Without Browser
- CI/CD runners (GitHub Actions, GitLab CI, Azure Pipelines)
- SSH servers
- Docker containers
- Remote development machines
- Production build agents

### Device Login Without Browser
```bash
workflo login --no-browser
```

**CLI outputs:**
```
To authenticate Workflo:

1. Open https://app.cortex.dev/device
2. Enter code: R7KM-L2QP

Waiting for browser approval...
```

User completes authorization on a different device (laptop, phone, etc.). CLI polls until approved or expired.

### CI/CD: Service Tokens (NOT interactive human refresh)
```bash
workflo auth service-token create
```

**Or create through Cortex dashboard.**

**Service Token Properties:**
- Workspace-scoped (not user-specific)
- Permission-scoped (not full access)
- Expiring (shorter lifetime than user refresh tokens)
- Revocable (via API or dashboard)
- Stored in CI secret manager (GitHub Secrets, GitLab CI Variables, etc.)
- Rotated automatically (recommended every 90 days)
- Visible in audit events

**Example GitHub Actions usage:**
```yaml
env:
  WORKFLO_TOKEN: ${{ secrets.WORKFLO_CI_TOKEN }}

workflo run:
  env:
    WORKFLO_TOKEN: ${{ env.WORKFLO_TOKEN }}
```

**Token must NOT be printed in logs.**

### Service Token Creation Flow
```bash
# Generate one-time token for CI
workflo auth service-token create --workspace engineering --scope workflo:runs:create

# Output (store in secret manager)
WORKFLO_CI_TOKEN=at_very_long_token_string

# Use in workflow
- name: Run workflo tests
  run: workflo run --repo <url> --test --security
  env:
    WORKFLO_TOKEN: ${{ secrets.WORKFLO_CI_TOKEN }}
```

## 12. Local-First Behavior

### Default: No Unexpected Upload
```text
Authentication: optional for purely local execution
Test execution: local
Repository contents: local
Receipt: local
Cloud publishing: disabled
```

### When User Explicitly Opts In
```bash
workflo run \
  --repo <url> \
  --test \
  --security \
  --publish
```

**Or:**
```bash
workflo receipt publish receipt.json
```

### CLI Must Clearly State When Data Leaves Machine
Every command that enables cloud features should have a `--publish` or equivalent flag, and the CLI must display a clear warning the first time such a flag is used.

**Example warning:**
```
⚠️  Cloud publishing enabled. Receipt and run metadata will be uploaded to Cortex.
This can be disabled with --no-publish flag.
```

**Cloud features when authenticated:**
- Receipt publishing
- Team history
- Usage tracking
- Organization policies
- Cloud dashboard

## 13. Device Login Backend Tables

### Minimal Authorization Schema (SQL)

```sql
CREATE TABLE oauth_device_sessions (
  id UUID PRIMARY KEY,
  client_id TEXT NOT NULL,
  device_code_hash TEXT UNIQUE NOT NULL,
  user_code_hash TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL,              -- "pending", "approved", "expired", "consumed"
  user_id UUID REFERENCES users(id),
  organization_id UUID REFERENCES organizations(id),
  workspace_id UUID REFERENCES workspaces(id),
  scopes TEXT[] NOT NULL,            -- granted OAuth scopes
  expires_at TIMESTAMPTZ NOT NULL,   -- device code expiry
  approved_at TIMESTAMPTZ,           -- when user approved
  consumed_at TIMESTAMPTZ,           -- when token exchanged
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Store Hashes, Not Raw Codes
```text
Raw device code → hash → database
```

**Rationale:** If database is exposed, attackers cannot immediately receive usable pending login codes.

```sql
CREATE TABLE oauth_refresh_tokens (
  id UUID PRIMARY KEY,
  token_hash TEXT UNIQUE NOT NULL,
  user_id UUID NOT NULL,
  client_id TEXT NOT NULL,
  organization_id UUID NOT NULL,
  workspace_id UUID,               -- may be NULL for service tokens
  scopes TEXT[] NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Refresh tokens also stored hashed or encrypted**, associated with a device record.

### Indexing for Performance
- `device_code_hash` UNIQUE index for lookups
- `user_code_hash` UNIQUE index (though user codes are short, protect against brute force)
- `expires_at` index for cleanup queries
- `revoked_at` index for active token queries

## 14. Audit Events

Record following every significant auth action:

```text
cli.device_authorization.started
cli.device_authorization.approved
cli.device_authorization.denied
cli.device_authorization.expired
cli.token.issued
cli.token.refreshed
cli.token.revoked
cli.workspace.selected
cli.service_token.used
```

### Each Event Must Include:
```json
{
  "type": "cli.device_authorization.approved",
  "user_id": "user_123",
  "organization_id": "org_456",
  "workspace_id": "ws_789",
  "client_id": "workflo_cli",
  "device_id": "device_abc",        -- hashed or random identifier
  "created_at": "2026-08-16T12:55:00Z",
  "ip_address": "203.0.113.45",     -- for security monitoring
  "user_agent": "Mozilla/5.0 ...",   -- for security monitoring
  "request_id": "req_abc123"        -- trace correlation
}
```

### Audit Event Storage
- Immutable log (append-only)
- Retained per compliance requirements (e.g., 90 days minimum)
- Searchable by user_id, organization_id, client_id, timestamp
- Exported for security investigations

## 15. Failure States

### Protocol States & User-Facing Output

```text
authorization_pending
```
**CLI output:**
```
Still waiting for approval...
```
**Behavior:** Continue polling at server-provided interval

```text
expired_token
```
**CLI output:**
```
The authorization request expired.
Run `workflo login` to start again.
```
**Behavior:** Clear all stored credentials, offer to restart flow

```text
access_denied
```
**CLI output:**
```
Access was denied.
No credentials were stored.
```
**Behavior:** No credentials saved; user must restart if they want to try again

```text
invalid_grant
```
**CLI output:**
```
Invalid authorization code or device code.
Run `workflo login` to start again.
```
**Behavior:** May indicate user re-approved or flow issue; restart recommended

```text
network_error
```
**CLI output:**
```
Network error during authorization.
Check internet connection and run `workflo login` again.
```
**Behavior:** Retry with exponential backoff, max 3 attempts

### Partially Issued Credentials
**Never leave partially issued credentials on failure.** If flow fails partway through:
1. Revoke any tokens issued before failure
2. Clear partial credentials from credential store
3. Display clear error message
4. Offer to restart flow

### User-Centric Error Messages
- **Why did this happen?** Explain in plain language
- **What can I do?** Give concrete next steps
- **Who do I contact?** Support info if needed (but not always)

## 16. Security Tests for Device Flow

### CI Tests Required
```text
Expired device code is rejected
Used device code cannot be reused
Wrong client cannot redeem device code
Wrong device code cannot approve another request
User code brute force is rate-limited
Polling faster than interval returns slow_down
Denied request never issues tokens
Token scopes cannot be expanded
Token cannot access another organization
Revoked membership blocks API use
Refresh token rotation detects reuse
Logout revokes the local session
```

### Cross-Tenant Test
```text
User from Organization Alpha approves a Workflo login,
then attempts to select Organization Beta.

Expected:
Only organizations where the user is a member appear.
```

**Rationale:** Prevents user from accidentally running commands in wrong tenant after approving in one organization.

## Recommended Flow (Complete Step-by-Step)

```text
1. User installs Workflo, ASTRA, or Nexus CLI (npm install -g).
2. User runs `<product> login`.
3. CLI requests a device code from Cortex Authorization Server.
4. Server returns: device_code, user_code, verification_uri, expires_in, interval.
5. CLI displays user_code and verification_uri in terminal.
6. CLI asks: "Open browser? [Y/n]"
7. If user accepts, CLI opens verification_uri in default browser.
8. User navigates to verification_uri, sees user_code prompt.
9. User enters/user_code (or it's pre-filled if browser redirect).
10. User signs in to Cortex account (with MFA if enabled).
11. User selects organization from dropdown (only their organizations).
12. User selects workspace from dropdown (workspaces under selected org).
13. User reviews requested scopes (product-specific, listed clearly).
14. User clicks "Approve device".
15. Authorization Server records approval: device_code → user_id, org_id, workspace_id, scopes.
16. CLI polls token endpoint at interval seconds.
17. After approval, server returns: access_token, refresh_token, token_type, expires_in, scope.
18. CLI stores refresh token in OS credential store (Keychain/WinCred/Secret Service).
19. CLI stores metadata (active_organization, active_workspace) in local profile.
20. CLI prints success:
    "Authenticated successfully.
    Organization: Cortex Labs
    Workspace: Workflo Engineering
    User: aarav@example.com"
21. Subsequent API requests use access_token in Authorization: Bearer header.
22. When access token expires (15 min), CLI uses refresh token to get new access token.
23. Logout revokes device credentials and clears OS credential store.
```

## Migration from Existing Auth

If existing users have API keys stored:

```bash
# Old flow (API key)
workflo run --api-key ts_live_...

# New flow (device login)
workflo login           # One-time setup
workflo run             # Uses stored credentials automatically
```

**Migration path:**
1. User runs `workflo login` — device flow starts
2. User completes browser approval
3. Credentials stored in OS credential store
4. Future runs use stored tokens; API key no longer needed
5. API key can be revoked separately via dashboard if desired

**Backward compatibility:**
- Old API keys still work until revoked
- New device login is opt-in (user runs `workflo login`)
- Both can coexist during transition period

## Design Decisions & Rationale

### Why OAuth 2.0 Device Authorization Grant (RFC 8628)?
- Designed specifically for CLIs and devices without convenient browser interfaces
- Follows pattern used by GitHub CLI, GitLab CLI, Homebrew, and other developer tools
- User doesn't need to paste passwords or long API tokens into terminal
- Works across operating systems with different credential stores

### Why Not PKCE-Only?
- Device flow + PKCE is the recommended combination per RFC 8628
- PKCE alone doesn't solve the "no browser" problem for CLI authentication
- Device flow provides the best UX for locally installed CLIs

### Why Separate Organization/Workspace Selection?
- Users often belong to multiple organizations/workspaces
- Prevents accidental commands in wrong tenant
- Clear separation between authentication (who you are) and tenancy (where you work)
- Matches how the existing control-plane API handles organization context

### Why OS Credential Stores?
- Native to each operating system
- Protected by OS-level security (Keychain, Credential Manager, Keyring)
- User expects this behavior from modern CLIs (GitHub CLI, Docker, etc.)
- Avoids storing secrets in plain config files or git

### Why Service Tokens for CI/CD?
- CI/CD runners are headless environments
- No interactive human to complete device flow
- Service tokens are workspace- and permission-scoped (least privilege)
- Stored in secret managers already used by CI systems
- Audit-visible for compliance

## Open Questions (to resolve with implementation team)

1. **Authorization server base URL:** `auth.cortex.dev`? Custom domain? Control-plane integrated?
2. **OAuth client ID per product:** `workflo_cli`, `astra_cli`, `nexus_cli`? Or shared?
3. **Scope naming convention:** `workflo:runs:create` vs `workflo-runs-create` vs different?
4. **Refresh token rotation enforcement:** Client-side or server-side? Both?
5. **Profile storage location:** `~/.config/cortex/`? `~/.tenant-shield/` (existing agent-cli path)?
6. **Audit event retention policy:** 90 days? 1 year? Compliance-driven?
7. **Cross-platform credential store fallback:** What if no Keychain/Credential Manager/Secret Service available?
8. **Service token creation UI:** Dashboard CLI? API only? `workflo auth service-token create`?
9. **Device code brute force protection:** CAPTCHA on verification page after N failed attempts?
10. **Token introspection endpoint:** Required for API gateways to validate tokens?

## Validation Checklist

- [ ] Device code lifetime ≤ 10 minutes, expires securely
- [ ] User code displayed in terminal, device code never displayed
- [ ] Polling interval respected (RFC 8628 compliant, "slow_down" handled)
- [ ] Access tokens short-lived (≈15 minutes), refresh tokens rotating
- [ ] Refresh tokens stored in OS credential store, never in plain config
- [ ] Profile system supports multiple accounts/organizations
- [ ] Scopes are product-specific and restricted (no unlimited access)
- [ ] Headless `--no-browser` flag works for CI/CD environments
- [ ] Service tokens for CI/CD are workspace-scoped and permission-scoped
- [ ] Local-first behavior: no unexpected upload without `--publish` flag
- [ ] Audit events recorded for all significant auth actions
- [ ] Failure states handled with clear user-facing messages
- [ ] Security tests cover all protocol states and cross-tenant scenarios
- [ ] No gradients, no glassmorphism, no purple/blue combinations (design requirement carries over to code comments/docs)
- [ ] Plain English copy throughout (no "revolutionize", "empower", "transform" in docs/user-facing text)
- [ ] Every number traceable (codebase numbers attributed, market data cited)