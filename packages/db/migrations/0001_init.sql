-- Workflo — Migration 0001_init
-- Authoritative control-plane state.
--
-- Trust classes:
--   A) Mutable control plane : organizations, projects, missions, github_connections (metadata)
--   B) Lifecycle resources   : runs (state transitions via SECURITY DEFINER functions only),
--                              findings (hypothesis -> judge verdict via function)
--   C) Append-only evidence  : evidence_events, audit_logs, inference_usage
--   D) Immutable crypto      : receipts
--
-- Tenancy: every tenant-owned table carries organization_id and is protected by
-- FORCE ROW LEVEL SECURITY. Missing tenant context fails closed.

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Roles (idempotent)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workflo_app') THEN
      CREATE ROLE workflo_app LOGIN PASSWORD 'workflo';
   END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Enumerated types (mirrored from packages/contracts — frozen alignment)
-- ---------------------------------------------------------------------------
CREATE TYPE run_state AS ENUM (
  'CREATED','INGESTING','PROVISIONING','EXECUTING','EXPLORING',
  'JUDGING','NOTARIZING','COMPLETED','FAILED'
);

CREATE TYPE agent_role AS ENUM (
  'ORCHESTRATOR','PROVISIONER','INGESTOR','EXECUTOR',
  'EXPLORER','TOOL_GATEWAY','JUDGE','NOTARY'
);

CREATE TYPE agent_event_kind AS ENUM (
  'MISSION_ACCEPTED','STATE_CHANGE','REPO_INGESTED','SANDBOX_PROVISIONED',
  'APP_STARTED','APP_HEALTHY','TEST_RESULTS','TOOL_PROPOSED','TOOL_AUTHORIZED',
  'TOOL_DENIED','TOOL_EXECUTED','OBSERVATION','HYPOTHESIS','REPRODUCTION',
  'CONTROL','FINDING_CONFIRMED','FINDING_UNCONFIRMED','RECEIPT_SIGNED',
  'TEARDOWN_VERIFIED','RUN_FAILED'
);

CREATE TYPE agent_event_status AS ENUM ('info','success','denied','error','timeout');

CREATE TYPE finding_status AS ENUM (
  'PROPOSED','CONFIRMED','UNCONFIRMED','INSUFFICIENT_CONTROL','ERROR'
);

CREATE TYPE finding_severity AS ENUM ('info','low','medium','high','critical');

CREATE TYPE judge_confidence AS ENUM ('low','medium','high');

CREATE TYPE audit_outcome AS ENUM ('success','denied','error');

CREATE TYPE member_role AS ENUM ('owner','admin','developer','viewer','auditor');

CREATE TYPE project_status AS ENUM ('ACTIVE','ARCHIVED');

CREATE TYPE mission_status AS ENUM ('DRAFT','ACTIVE','ARCHIVED');

-- ---------------------------------------------------------------------------
-- Tenant context helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION current_org_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION current_user_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------------------
-- Tables (FK order)
-- ---------------------------------------------------------------------------

CREATE TABLE organizations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
  slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  display_name  text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz
);

CREATE TABLE memberships (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role            member_role NOT NULL DEFAULT 'developer',
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id)
);

CREATE TABLE projects (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
  slug            text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  description     text NOT NULL DEFAULT '',
  status          project_status NOT NULL DEFAULT 'ACTIVE',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, slug)
);

-- GitHub connections: credential material is stored ONLY as a reference
-- (vault://, kms://, sm:// or file:// for dev). Raw tokens CANNOT satisfy the
-- CHECK constraint and are rejected at the database layer.
CREATE TABLE github_connections (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid REFERENCES projects(id),
  provider        text NOT NULL DEFAULT 'github' CHECK (provider = 'github'),
  installation_id text NOT NULL,
  repository_id   text,
  repository_url  text,
  account_login   text,
  default_ref     text,
  credential_ref  text NOT NULL
    CHECK (
      credential_ref ~ '^(vault|kms|sm|file)://'
      AND credential_ref NOT LIKE 'ghp\_%'
      AND credential_ref NOT LIKE 'gho\_%'
      AND credential_ref NOT LIKE 'github\_pat\_%'
    ),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE missions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid NOT NULL REFERENCES projects(id),
  created_by      uuid REFERENCES users(id),
  title           text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 300),
  intent          text NOT NULL,
  status          mission_status NOT NULL DEFAULT 'DRAFT',
  config          jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Runs: lifecycle resource. Direct UPDATE of `state` is NOT granted to the
-- application role; transitions go through transition_run_state().
CREATE TABLE runs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid NOT NULL REFERENCES projects(id),
  mission_id      uuid NOT NULL REFERENCES missions(id),
  created_by      uuid REFERENCES users(id),
  state           run_state NOT NULL DEFAULT 'CREATED',
  sandbox_id      text,
  error           text,
  started_at      timestamptz,
  finished_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Append-only evidence ledger (Class C).
-- Columns mirror PublicAgentEventSchema exactly (no second taxonomy).
CREATE TABLE evidence_events (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq                 bigint GENERATED ALWAYS AS IDENTITY,
  organization_id     uuid NOT NULL REFERENCES organizations(id),
  project_id          uuid NOT NULL REFERENCES projects(id),
  run_id              uuid NOT NULL REFERENCES runs(id),
  event_type          agent_event_kind NOT NULL,
  role                agent_role NOT NULL,
  status              agent_event_status NOT NULL,
  parent_event_id     uuid REFERENCES evidence_events(id),
  request_id          uuid,
  action              text CHECK (action IS NULL OR char_length(action) <= 200),
  summary             text NOT NULL CHECK (char_length(summary) <= 500),
  rationale           text CHECK (rationale IS NULL OR char_length(rationale) <= 500),
  observation_summary text CHECK (observation_summary IS NULL OR char_length(observation_summary) <= 2000),
  policy_id           text CHECK (policy_id IS NULL OR char_length(policy_id) <= 200),
  payload             jsonb NOT NULL DEFAULT '{}',
  prev_hash           text,
  hash                text,
  occurred_at         timestamptz NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- Findings: explorer hypothesis (PROPOSED) -> judge verdict via judge_finding().
-- Once judged, the finding is immutable.
CREATE TABLE findings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid NOT NULL REFERENCES projects(id),
  run_id          uuid NOT NULL REFERENCES runs(id),
  title           text NOT NULL CHECK (char_length(title) <= 300),
  summary         text NOT NULL DEFAULT '' CHECK (char_length(summary) <= 2000),
  severity        finding_severity NOT NULL DEFAULT 'info',
  status          finding_status NOT NULL DEFAULT 'PROPOSED',
  confidence      judge_confidence,
  evidence_refs   uuid[] NOT NULL DEFAULT '{}',
  decided_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Receipts (Class D): immutable. One per run.
CREATE TABLE receipts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid NOT NULL REFERENCES projects(id),
  run_id          uuid NOT NULL UNIQUE REFERENCES runs(id),
  receipt_version smallint NOT NULL CHECK (receipt_version = 4),
  payload         jsonb NOT NULL,
  payload_sha256  text NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
  signature       text NOT NULL,
  key_id          text NOT NULL,
  log_id          text,
  log_checkpoint  bigint CHECK (log_checkpoint IS NULL OR log_checkpoint >= 0),
  merkle_root     text,
  issued_at       timestamptz NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Audit logs (Class C): append-only. Written via a dedicated connection so a
-- caller's ROLLBACK cannot erase denied/failed security operations.
CREATE TABLE audit_logs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid REFERENCES projects(id),
  actor_user_id   uuid REFERENCES users(id),
  actor_label     text NOT NULL,
  action          text NOT NULL,
  resource_type   text NOT NULL,
  resource_id     text,
  outcome         audit_outcome NOT NULL,
  request_id      uuid,
  metadata        jsonb NOT NULL DEFAULT '{}',
  occurred_at     timestamptz NOT NULL DEFAULT now()
);

-- Inference usage telemetry (Class C): measurements only, no billing math.
CREATE TABLE inference_usage (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL REFERENCES organizations(id),
  project_id        uuid NOT NULL REFERENCES projects(id),
  run_id            uuid NOT NULL REFERENCES runs(id),
  model_id          text NOT NULL,
  model_version     text,
  request_id        text NOT NULL,
  input_tokens      integer NOT NULL CHECK (input_tokens >= 0),
  output_tokens     integer NOT NULL CHECK (output_tokens >= 0),
  inference_seconds numeric(12,3) NOT NULL CHECK (inference_seconds >= 0),
  queue_seconds     numeric(12,3) NOT NULL DEFAULT 0 CHECK (queue_seconds >= 0),
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX memberships_org_idx    ON memberships (organization_id);
CREATE INDEX memberships_user_idx   ON memberships (user_id);
CREATE INDEX projects_org_idx       ON projects (organization_id);
CREATE INDEX ghc_org_idx            ON github_connections (organization_id);
CREATE INDEX missions_org_idx       ON missions (organization_id);
CREATE INDEX missions_project_idx   ON missions (project_id);
CREATE INDEX runs_org_idx           ON runs (organization_id);
CREATE INDEX runs_project_idx       ON runs (project_id);
CREATE INDEX runs_mission_idx       ON runs (mission_id);
CREATE INDEX runs_state_idx         ON runs (state);
CREATE INDEX evidence_org_idx       ON evidence_events (organization_id);
CREATE INDEX evidence_run_seq_idx   ON evidence_events (run_id, seq);
CREATE INDEX evidence_type_idx      ON evidence_events (event_type);
CREATE INDEX findings_org_idx       ON findings (organization_id);
CREATE INDEX findings_run_idx       ON findings (run_id);
CREATE INDEX receipts_org_idx       ON receipts (organization_id);
CREATE INDEX audit_org_idx          ON audit_logs (organization_id, occurred_at);
CREATE INDEX audit_resource_idx     ON audit_logs (resource_type, resource_id);
CREATE INDEX usage_org_idx          ON inference_usage (organization_id);
CREATE INDEX usage_run_idx          ON inference_usage (run_id);

-- ---------------------------------------------------------------------------
-- updated_at helper for mutable (Class A) tables
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$$;

CREATE TRIGGER organizations_touch BEFORE UPDATE ON organizations
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER projects_touch BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER github_connections_touch BEFORE UPDATE ON github_connections
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER missions_touch BEFORE UPDATE ON missions
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------------------------------------------------------------------------
-- Append-only guards (defense in depth; privileges are the primary control)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only: % not allowed', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'raise_exception';
END
$$;

CREATE TRIGGER evidence_events_append_only BEFORE UPDATE OR DELETE ON evidence_events
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER inference_usage_append_only BEFORE UPDATE OR DELETE ON inference_usage
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER receipts_immutable BEFORE UPDATE OR DELETE ON receipts
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- Judged findings are immutable (judge_finding performs the single legal
-- status change while the row is still PROPOSED; this trigger fires after it
-- and blocks any later content mutation).
CREATE OR REPLACE FUNCTION findings_immutability_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'PROPOSED' THEN
    IF NEW.status IS DISTINCT FROM OLD.status
       OR NEW.title IS DISTINCT FROM OLD.title
       OR NEW.summary IS DISTINCT FROM OLD.summary
       OR NEW.severity IS DISTINCT FROM OLD.severity
       OR NEW.confidence IS DISTINCT FROM OLD.confidence
       OR NEW.evidence_refs IS DISTINCT FROM OLD.evidence_refs
       OR NEW.decided_at IS DISTINCT FROM OLD.decided_at THEN
      RAISE EXCEPTION 'judged findings are immutable';
    END IF;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END
$$;

CREATE TRIGGER findings_guard BEFORE UPDATE ON findings
  FOR EACH ROW EXECUTE FUNCTION findings_immutability_guard();

-- ---------------------------------------------------------------------------
-- Lifecycle transition functions (SECURITY DEFINER; explicit tenant check
-- inside because the owner bypasses RLS)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION transition_run_state(
  p_run_id uuid,
  p_new_state run_state,
  p_meta jsonb DEFAULT '{}'::jsonb
) RETURNS runs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_org uuid;
  v_row_org uuid;
  v_cur run_state;
  v_ok boolean;
  v_row public.runs;
BEGIN
  v_org := NULLIF(current_setting('app.current_org_id', true), '')::uuid;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'tenant context is required';
  END IF;

  SELECT organization_id, state INTO v_row_org, v_cur
  FROM runs WHERE id = p_run_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'run not found';
  END IF;

  IF v_row_org <> v_org THEN
    RAISE EXCEPTION 'cross-tenant access denied';
  END IF;

  v_ok := CASE v_cur
    WHEN 'CREATED'      THEN p_new_state IN ('INGESTING','FAILED')
    WHEN 'INGESTING'    THEN p_new_state IN ('PROVISIONING','FAILED')
    WHEN 'PROVISIONING' THEN p_new_state IN ('EXECUTING','FAILED')
    WHEN 'EXECUTING'    THEN p_new_state IN ('EXPLORING','FAILED')
    WHEN 'EXPLORING'    THEN p_new_state IN ('JUDGING','FAILED')
    WHEN 'JUDGING'      THEN p_new_state IN ('NOTARIZING','FAILED')
    WHEN 'NOTARIZING'   THEN p_new_state IN ('COMPLETED','FAILED')
    ELSE false
  END;

  IF NOT v_ok THEN
    RAISE EXCEPTION 'illegal run transition: % -> %', v_cur, p_new_state;
  END IF;

  UPDATE runs SET
    state       = p_new_state,
    updated_at  = now(),
    started_at  = CASE
                    WHEN v_cur = 'CREATED' AND started_at IS NULL THEN now()
                    ELSE started_at
                  END,
    finished_at = CASE
                    WHEN p_new_state IN ('COMPLETED','FAILED') THEN now()
                    ELSE finished_at
                  END,
    sandbox_id  = COALESCE(p_meta->>'sandbox_id', sandbox_id),
    error       = CASE
                    WHEN p_new_state = 'FAILED' THEN p_meta->>'error'
                    ELSE error
                  END
  WHERE id = p_run_id
  RETURNING * INTO v_row;

  RETURN v_row;
END
$$;

CREATE OR REPLACE FUNCTION judge_finding(
  p_finding_id uuid,
  p_verdict finding_status,
  p_confidence judge_confidence DEFAULT NULL,
  p_evidence_refs uuid[] DEFAULT '{}'
) RETURNS findings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_org uuid;
  v_row public.findings;
  v_ref_count integer;
BEGIN
  v_org := NULLIF(current_setting('app.current_org_id', true), '')::uuid;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'tenant context is required';
  END IF;

  IF p_verdict = 'PROPOSED' THEN
    RAISE EXCEPTION 'judge verdict cannot be PROPOSED';
  END IF;

  SELECT * INTO v_row FROM findings WHERE id = p_finding_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'finding not found';
  END IF;

  IF v_row.organization_id <> v_org THEN
    RAISE EXCEPTION 'cross-tenant access denied';
  END IF;

  IF v_row.status <> 'PROPOSED' THEN
    RAISE EXCEPTION 'finding already judged: %', v_row.status;
  END IF;

  -- The judge may only reference evidence that exists in this tenant's
  -- ledger for this run.
  SELECT count(*) INTO v_ref_count
  FROM evidence_events
  WHERE id = ANY (p_evidence_refs)
    AND organization_id = v_org
    AND run_id = v_row.run_id;

  IF v_ref_count <> cardinality(p_evidence_refs) THEN
    RAISE EXCEPTION 'evidence_refs must reference ledger events of this run';
  END IF;

  UPDATE findings SET
    status        = p_verdict,
    confidence    = p_confidence,
    evidence_refs = p_evidence_refs,
    decided_at    = now()
  WHERE id = p_finding_id
  RETURNING * INTO v_row;

  RETURN v_row;
END
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security: enable + FORCE on every tenant-owned table
-- ---------------------------------------------------------------------------
ALTER TABLE organizations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations       FORCE  ROW LEVEL SECURITY;
ALTER TABLE users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE users               FORCE  ROW LEVEL SECURITY;
ALTER TABLE memberships         ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships         FORCE  ROW LEVEL SECURITY;
ALTER TABLE projects            ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects            FORCE  ROW LEVEL SECURITY;
ALTER TABLE github_connections  ENABLE ROW LEVEL SECURITY;
ALTER TABLE github_connections  FORCE  ROW LEVEL SECURITY;
ALTER TABLE missions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions            FORCE  ROW LEVEL SECURITY;
ALTER TABLE runs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs                FORCE  ROW LEVEL SECURITY;
ALTER TABLE evidence_events     ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_events     FORCE  ROW LEVEL SECURITY;
ALTER TABLE findings            ENABLE ROW LEVEL SECURITY;
ALTER TABLE findings            FORCE  ROW LEVEL SECURITY;
ALTER TABLE receipts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE receipts            FORCE  ROW LEVEL SECURITY;
ALTER TABLE audit_logs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs          FORCE  ROW LEVEL SECURITY;
ALTER TABLE inference_usage     ENABLE ROW LEVEL SECURITY;
ALTER TABLE inference_usage     FORCE  ROW LEVEL SECURITY;

-- organizations: members can see their orgs; service may create orgs.
CREATE POLICY orgs_member_select ON organizations FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM memberships m
    WHERE m.organization_id = organizations.id
      AND m.user_id = current_user_id()
  ));
CREATE POLICY orgs_insert ON organizations FOR INSERT
  WITH CHECK (true);
CREATE POLICY orgs_member_update ON organizations FOR UPDATE
  USING (EXISTS (
    SELECT 1 FROM memberships m
    WHERE m.organization_id = organizations.id
      AND m.user_id = current_user_id()
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM memberships m
    WHERE m.organization_id = organizations.id
      AND m.user_id = current_user_id()
  ));

-- users: self-visible + members of same org may read; creation is open to the
-- service role (authentication layer gates who may call it).
CREATE POLICY users_self_select ON users FOR SELECT
  USING (
    id = current_user_id()
    OR EXISTS (
      SELECT 1 FROM memberships m
      WHERE m.user_id = users.id
        AND m.organization_id = current_org_id()
    )
  );
CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (true);

-- memberships: tenant-scoped; creator membership seeded by service.
CREATE POLICY memberships_tenant ON memberships FOR ALL
  USING (organization_id = current_org_id() OR user_id = current_user_id())
  WITH CHECK (organization_id = current_org_id());

-- Standard tenant isolation for everything else.
CREATE POLICY projects_tenant ON projects FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY ghc_tenant ON github_connections FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY missions_tenant ON missions FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY runs_tenant ON runs FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY evidence_tenant ON evidence_events FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY findings_tenant ON findings FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY receipts_tenant ON receipts FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY audit_tenant ON audit_logs FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

CREATE POLICY usage_tenant ON inference_usage FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

-- ---------------------------------------------------------------------------
-- Grants for the application role
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO workflo_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO workflo_app;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO workflo_app;

GRANT INSERT ON users, organizations, memberships, projects,
  github_connections, missions, runs, findings TO workflo_app;
GRANT INSERT ON evidence_events, audit_logs, inference_usage, receipts
  TO workflo_app;

-- Class A mutations (column-scoped; updated_at is trigger-managed).
GRANT UPDATE (name) ON organizations TO workflo_app;
GRANT UPDATE (name, description, status) ON projects TO workflo_app;
GRANT UPDATE (title, intent, status, config) ON missions TO workflo_app;
GRANT UPDATE (repository_url, default_ref, credential_ref) ON github_connections TO workflo_app;
-- Pre-judgment finding edits only; verdict fields via judge_finding().
GRANT UPDATE (title, summary, severity) ON findings TO workflo_app;
-- memberships: join/leave managed by service.
GRANT DELETE ON memberships, github_connections TO workflo_app;

-- Lifecycle functions.
GRANT EXECUTE ON FUNCTION transition_run_state(uuid, run_state, jsonb) TO workflo_app;
GRANT EXECUTE ON FUNCTION judge_finding(uuid, finding_status, judge_confidence, uuid[]) TO workflo_app;

-- ---------------------------------------------------------------------------
-- Migration bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  name        text PRIMARY KEY,
  sha256      text NOT NULL,
  applied_at  timestamptz NOT NULL DEFAULT now()
);

COMMIT;
