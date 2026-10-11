-- Workflo — Migration 0002_evidence_chain
-- Turns evidence_events into a per-run hash-chained, tamper-evident ledger.
--
--   * per-run sequence  : UNIQUE(run_id, run_seq) over chained events
--   * chain linkage     : prev_hash / hash columns written by the ledger
--   * atomic allocation : append_evidence_event() locks the run row, verifies
--                         chain head + sequence, inserts — all in one statement
--   * write path closed : workflo_app loses direct INSERT on evidence_events
--   * consumer offsets  : idempotent consumers (consumer_id, event_id)
--   * run projections   : rebuildable derived state per run
--
-- Genesis anchor (must match packages/events hash-chain.ts):
--   sha256("workflo:evidence:genesis:v1")
--   = 70cf1f39fae1b99f421d5265cda76dd56907e8d4966b27ad9035d1301a822b74

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Per-run sequence on evidence_events
-- ---------------------------------------------------------------------------
ALTER TABLE evidence_events ADD COLUMN run_seq bigint;

-- Backfill pre-chain rows (none exist in production; dev/test DBs only).
UPDATE evidence_events e
SET run_seq = t.rn
FROM (
  SELECT id, row_number() OVER (PARTITION BY run_id ORDER BY seq) AS rn
  FROM evidence_events
) t
WHERE e.id = t.id AND e.run_seq IS NULL;

-- Chained events are unique per (run, run_seq); unchained legacy rows stay
-- visible but are flagged invalid by chain verification.
CREATE UNIQUE INDEX evidence_events_run_seq_uq
  ON evidence_events (run_id, run_seq)
  WHERE run_seq IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Atomic, tenant-bound, chain-validating append function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION append_evidence_event(p jsonb)
RETURNS evidence_events
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  c_genesis CONSTANT text := '70cf1f39fae1b99f421d5265cda76dd56907e8d4966b27ad9035d1301a822b74';
  v_org uuid;
  v_run_org uuid;
  v_run_id uuid := (p->>'run_id')::uuid;
  v_run_project uuid;
  v_prev_hash text;
  v_latest_hash text;
  v_expected_seq bigint;
  v_row evidence_events;
BEGIN
  v_org := NULLIF(current_setting('app.current_org_id', true), '')::uuid;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'tenant context is required';
  END IF;

  -- Serialize concurrent appends for this run WITHOUT needing UPDATE
  -- privileges (workflo_app deliberately has none on runs).
  PERFORM pg_advisory_xact_lock(hashtextextended(v_run_id::text, 0));

  -- Lock the run row (owner-privileged inside this SECURITY DEFINER fn).
  SELECT organization_id, project_id INTO v_run_org, v_run_project
  FROM runs WHERE id = v_run_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'run not found';
  END IF;

  IF v_run_org <> v_org THEN
    RAISE EXCEPTION 'cross-tenant access denied';
  END IF;

  -- Latest chained event for this run.
  SELECT hash INTO v_latest_hash
  FROM evidence_events
  WHERE run_id = v_run_id AND hash IS NOT NULL AND run_seq IS NOT NULL
  ORDER BY run_seq DESC
  LIMIT 1;

  v_prev_hash := COALESCE(v_latest_hash, c_genesis);

  -- Chain linkage must match the supplied values.
  IF (p->>'prev_hash') IS DISTINCT FROM v_prev_hash THEN
    RAISE EXCEPTION 'evidence chain conflict: prev_hash mismatch (stale read)';
  END IF;

  v_expected_seq := COALESCE((
    SELECT MAX(run_seq) FROM evidence_events
    WHERE run_id = v_run_id AND run_seq IS NOT NULL
  ), 0) + 1;

  IF (p->>'run_seq')::bigint IS DISTINCT FROM v_expected_seq THEN
    RAISE EXCEPTION 'evidence chain conflict: expected run_seq %, got %',
      v_expected_seq, p->>'run_seq';
  END IF;

  INSERT INTO evidence_events (
    id, organization_id, project_id, run_id, run_seq,
    event_type, role, status,
    parent_event_id, request_id, action, summary, rationale,
    observation_summary, policy_id, payload,
    prev_hash, hash, occurred_at
  ) VALUES (
    (p->>'id')::uuid,
    v_org,
    v_run_project,
    v_run_id,
    v_expected_seq,
    (p->>'event_type')::agent_event_kind,
    (p->>'role')::agent_role,
    (p->>'status')::agent_event_status,
    NULLIF(p->>'parent_event_id', '')::uuid,
    NULLIF(p->>'request_id', '')::uuid,
    p->>'action',
    p->>'summary',
    p->>'rationale',
    p->>'observation_summary',
    p->>'policy_id',
    COALESCE(p->'payload', '{}'::jsonb),
    v_prev_hash,
    p->>'hash',
    (p->>'occurred_at')::timestamptz
  )
  RETURNING * INTO v_row;

  RETURN v_row;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Close the raw write path: app role can no longer INSERT directly.
--    All evidence flows through append_evidence_event().
-- ---------------------------------------------------------------------------
REVOKE INSERT ON evidence_events FROM workflo_app;
GRANT EXECUTE ON FUNCTION append_evidence_event(jsonb) TO workflo_app;

-- ---------------------------------------------------------------------------
-- 4. Consumer offsets — idempotent consumer bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE consumer_offsets (
  consumer_id     text NOT NULL,
  event_id        uuid NOT NULL REFERENCES evidence_events(id),
  organization_id uuid NOT NULL,
  processed_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_id, event_id)
);

ALTER TABLE consumer_offsets ENABLE ROW LEVEL SECURITY;
ALTER TABLE consumer_offsets FORCE  ROW LEVEL SECURITY;
CREATE POLICY consumer_offsets_tenant ON consumer_offsets FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

GRANT SELECT, INSERT ON consumer_offsets TO workflo_app;

-- ---------------------------------------------------------------------------
-- 5. Run projections — rebuildable derived state (never authoritative)
-- ---------------------------------------------------------------------------
CREATE TABLE run_projections (
  run_id          uuid PRIMARY KEY REFERENCES runs(id),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  project_id      uuid NOT NULL REFERENCES projects(id),
  state           jsonb NOT NULL,
  last_run_seq    bigint NOT NULL DEFAULT 0,
  updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE run_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_projections FORCE  ROW LEVEL SECURITY;
CREATE POLICY run_projections_tenant ON run_projections FOR ALL
  USING (organization_id = current_org_id())
  WITH CHECK (organization_id = current_org_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON run_projections TO workflo_app;

COMMIT;
