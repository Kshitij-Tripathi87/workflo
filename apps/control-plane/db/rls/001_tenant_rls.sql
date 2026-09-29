-- 001_tenant_rls.sql — PostgreSQL Row-Level Security (defense in depth).
--
-- SOC 2 CC6.1/CC6.7: tenant isolation is enforced by application code
-- (every query is project-scoped); THESE policies are the tripwire that
-- turns an application bug into a denial instead of a data leak.
--
-- Applying:
--   psql $DATABASE_URL -f db/rls/001_tenant_rls.sql
--
-- Operating model:
--   * The application connects as a NON-owner role (e.g. workflo_api).
--     FORCE ROW LEVEL SECURITY makes the policies apply even to the table
--     owner; keep migrations on the owner role (BYPASSRLS) instead.
--   * Every request-scoped session sets the tenant before querying:
--         SELECT set_config('app.current_project_id', '<project uuid>', true);
--     (transaction-local: resets automatically; no cross-request leakage
--     possible through the connection pool.) The app does this in
--     app.db.database.set_tenant_context.
--   * When the GUC is unset/empty, NULLIF(...) is NULL and every predicate
--    `= NULL` is false — DENY BY DEFAULT. Pre-RLS bootstrap scripts run
--    as the owner role.
--
-- Verify after applying (evidence for auditors):
--   SELECT relname, relrowsecurity FROM pg_class WHERE relname IN
--     ('projects','api_keys','test_runs','test_results','artifacts','audit_events');
--   -- As workflo_api with no GUC set: SELECT * FROM test_runs; -- 0 rows

BEGIN;

ALTER TABLE projects    ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects    FORCE ROW LEVEL SECURITY;
ALTER TABLE api_keys    ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys    FORCE ROW LEVEL SECURITY;
ALTER TABLE test_runs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_runs   FORCE ROW LEVEL SECURITY;
ALTER TABLE test_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_results FORCE ROW LEVEL SECURITY;
ALTER TABLE artifacts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts   FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

-- projects: the row IS the tenant.
CREATE POLICY tenant_isolation_projects ON projects
    USING (id = NULLIF(current_setting('app.current_project_id', true), ''))
    WITH CHECK (id = NULLIF(current_setting('app.current_project_id', true), ''));

-- api_keys: scoped by project_id.
CREATE POLICY tenant_isolation_api_keys ON api_keys
    USING (project_id = NULLIF(current_setting('app.current_project_id', true), ''))
    WITH CHECK (project_id = NULLIF(current_setting('app.current_project_id', true), ''));

-- test_runs: scoped by project_id.
CREATE POLICY tenant_isolation_test_runs ON test_runs
    USING (project_id = NULLIF(current_setting('app.current_project_id', true), ''))
    WITH CHECK (project_id = NULLIF(current_setting('app.current_project_id', true), ''));

-- test_results / artifacts: scoped through their parent run.
CREATE POLICY tenant_isolation_test_results ON test_results
    USING (run_id IN (SELECT id FROM test_runs
                      WHERE project_id = NULLIF(current_setting('app.current_project_id', true), '')))
    WITH CHECK (run_id IN (SELECT id FROM test_runs
                           WHERE project_id = NULLIF(current_setting('app.current_project_id', true), '')));

CREATE POLICY tenant_isolation_artifacts ON artifacts
    USING (run_id IN (SELECT id FROM test_runs
                      WHERE project_id = NULLIF(current_setting('app.current_project_id', true), '')))
    WITH CHECK (run_id IN (SELECT id FROM test_runs
                           WHERE project_id = NULLIF(current_setting('app.current_project_id', true), '')));

-- audit_events: reads are tenant-scoped; inserts are allowed from any
-- authenticated session (rows are attributed server-side, and a denied
-- cross-tenant attempt must still be writable as an audit event).
CREATE POLICY tenant_isolation_audit_select ON audit_events
    FOR SELECT
    USING (project_id = NULLIF(current_setting('app.current_project_id', true), ''));

CREATE POLICY tenant_isolation_audit_insert ON audit_events
    FOR INSERT
    WITH CHECK (true);

COMMIT;
