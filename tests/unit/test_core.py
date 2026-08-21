"""Unit tests for Tenant Shield core: patterns, records, adapters, results schema, CLI.

These are pure-Python tests: no Playwright, no mock server, no network.
They run in seconds and validate the logic of the new Phase 1 modules."""

import json
import os
import tempfile

import pytest

from workflo.isolation.patterns import IsolationPattern
from workflo.isolation.result import VerificationRecord, VerificationSummary
from workflo.isolation.verifier import (
    verify_read,
    verify_list_excludes,
    verify_modify_denied,
    verify_delete_denied,
    verify_positive_control,
    verify_cross_tenant_access,
    assert_summary,
    _tenants_of,
)
from workflo.adapters import (
    AdapterRegistry,
    TenantAwareRequest,
    HeaderTenantResolver,
    SubdomainTenantResolver,
    JWTTenantResolver,
    BearerAuthProvider,
    SessionAuthProvider,
    APIKeyAuthProvider,
)
from workflo.reporting.results import RunReport, TestResult
from workflo.reporting.compliance_report import (
    build_context,
    _short,
    _pass_rate,
    _read_history,
    _append_history,
    _control_mappings,
)
from workflo.cli import _split_results_arg


class DummyClient:
    """Trivial client the verifier can drive without network."""

    def __init__(self, tenant_id, status_map=None):
        self.tenant_id = tenant_id
        self._status_map = status_map or {}
        self.calls = []
        self._responses = []

    def _call(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        key = f"{method}:{path}"
        status = self._status_map.get(key, 200)
        body = {"projects": [{"id": "own-1"}, {"id": "own-2"}]}
        dr = DummyResponse(status, body, key)
        self._responses.append(dr)
        return dr

    def get(self, path, **kw):
        return self._call("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self._call("POST", path, json=json, **kw)

    def put(self, path, json=None, **kw):
        return self._call("PUT", path, json=json, **kw)

    def delete(self, path, **kw):
        return self._call("DELETE", path, **kw)


class DummyResponse:
    def __init__(self, status_code, body, key=""):
        self.status_code = status_code
        self._body = body
        self._key = key

    def json(self):
        # List calls get a dict; read calls get a dict per status_code convention
        if self._key.startswith("GET:") and "/api/v1/projects" == self._key.split(":")[1]:
            return self._body
        return self._body if isinstance(self._body, dict) else {"id": "x", "name": "x"}
    raise_for_status = lambda s: None if s.status_code < 400 else (_ for _ in ()).throw(Exception("HTTP error"))


def test_pattern_enum_values():
    assert IsolationPattern.API_READ.value == "api_read"
    assert IsolationPattern.POSITIVE_CONTROL.value == "positive_control"
    assert len(list(IsolationPattern)) == 7


def test_pattern_soc2_mappings():
    assert "CC6.1" in IsolationPattern.API_DELETE.soc2_controls
    assert "CC6.6" in IsolationPattern.API_READ.soc2_controls
    assert "CC6.1" in IsolationPattern.POSITIVE_CONTROL.soc2_controls


def test_pattern_labels_not_empty():
    for p in IsolationPattern:
        assert len(p.label) > 0, p.value


def test_verification_record():
    r = VerificationRecord(
        pattern="api_read",
        assertion="GET /x -> (403)",
        expected=[403, 404],
        actual_status=403,
        passed=True,
        tenant_pair=["c1", "c2"],
        resource_id="rid",
    )
    d = r.to_dict()
    assert d["pattern"] == "api_read"
    assert d["passed"] is True
    assert d["tenant_pair"] == ["c1", "c2"]


def test_verification_summary_passed():
    s = VerificationSummary(creator_tenant="a", intruder_tenant="b", resource_id="r")
    s.records.append(VerificationRecord(
        pattern="api_read", assertion="", expected=[403], actual_status=403,
        passed=True, tenant_pair=[], resource_id="r"))
    s.records.append(VerificationRecord(
        pattern="api_list", assertion="", expected=[], actual_status=200,
        passed=True, tenant_pair=[], resource_id="r"))
    assert s.passed
    assert len(s.records) == 2
    assert "creator_tenant" in s.to_dict()


def test_tenants_of():
    c = DummyClient("acme")
    i = DummyClient("globex")
    assert _tenants_of(c, i) == ("acme", "globex")
    assert _tenants_of(None, i) == ("creator", "globex")


def test_verifier_include_subset():
    c = DummyClient("acme")
    intruder = DummyClient("globex")
    summary = verify_cross_tenant_access(
        c, intruder, "proj-1", include=["read", "positive"], expected_denial_statuses=(403,)
    )
    # Only selected patterns
    patterns = {r.pattern for r in summary.records}
    assert patterns == {"api_read", "positive_control"}


def test_assert_summary_on_failure():
    r = VerificationRecord(
        pattern="x", assertion="bad", expected=403, actual_status=200,
        passed=False, tenant_pair=[], resource_id="r")
    s = VerificationSummary(creator_tenant="a", intruder_tenant="b", resource_id="r",
                            records=[r])
    with pytest.raises(AssertionError, match="bad"):
        assert_summary(s)


class TestAdapters:
    def test_header_resolver(self):
        r = HeaderTenantResolver({"header_name": "X-Custom-Tenant"})
        req = TenantAwareRequest("http://x.com", "/p")
        r.apply(req, "t1")
        assert req.headers["X-Custom-Tenant"] == "t1"

    def test_subdomain_resolver(self):
        r = SubdomainTenantResolver({"base_host": "app.example.com"})
        req = TenantAwareRequest("https://app.example.com", "/p")
        r.apply(req, "t1")
        assert "t1.app.example.com" in req.base_url
        assert req.path == "/p"

    def test_subdomain_prefix_mode(self):
        r = SubdomainTenantResolver({"mode": "prefix"})
        req = TenantAwareRequest("https://x.com", "/path")
        r.apply(req, "t1")
        assert req.path == "/t1/path"

    def test_jwt_resolver(self):
        r = JWTTenantResolver()
        token_header = (
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJ0ZW5hbnRfaWQiOiJhY21lIn0.sig"
        )
        req = TenantAwareRequest("https://x.com", "/p", {"Authorization": token_header})
        r.apply(req, "")
        assert req.headers.get("X-Tenant-ID") == "acme"

    def test_jwt_resolver_explicit_overrides(self):
        r = JWTTenantResolver()
        req = TenantAwareRequest("https://x.com", "/p", {"Authorization": "Bearer jwt.wrong"})
        r.apply(req, "explicit-tenant")
        assert req.headers["X-Tenant-ID"] == "explicit-tenant"

    def test_bearer_auth(self):
        p = BearerAuthProvider()
        h = p.auth_headers("tok")
        assert h["Authorization"] == "Bearer tok"

    def test_session_auth(self):
        p = SessionAuthProvider()
        h = p.auth_headers("u@c.com")
        assert "Cookie" in h
        assert "session_email=u@c.com" in h["Cookie"]

    def test_api_key_auth(self):
        p = APIKeyAuthProvider({"header_name": "X-Api-Key"})
        h = p.auth_headers("k-123")
        assert h["X-Api-Key"] == "k-123"

    def test_registry_builds_defaults(self):
        reg = AdapterRegistry()
        resolver, provider = reg.build({})
        assert resolver.name == "header"
        assert provider.name == "bearer"


class TestReporting:
    def test_short_utility(self):
        assert _short("abc123-def") == "abc123"

    def test_pass_rate(self):
        assert _pass_rate({"total": 10, "passed": 9}) == 90

    def test_run_report_serialization(self):
        rr = RunReport.new(suite="custom")
        rr.results.append(TestResult(
            test_name="t1", nodeid="t1", status="passed",
            assertion="GET /x -> 403", tenant_pair=["c1", "c2"],
            soc2_controls=["CC6.1"], pattern="api_read", actual_status=403,
        ))
        assert rr.summary["failed"] == 0
        assert rr.summary["positive_controls_passed"] == 0
        j = rr.to_json()
        d2 = json.loads(j)
        assert d2["suite"] == "custom"

    def test_run_report_roundtrip(self):
        rr = RunReport.new()
        rr.results.append(TestResult(
            test_name="t", nodeid="t",
            status="failed", assertion="foo", tenant_pair=["a", "b"],
            soc2_controls=["CC6.6"], pattern="api_read", actual_status=200, error="bad",
        ))
        rr2 = RunReport.from_dict(rr.to_dict())
        assert rr2.summary["failed"] == 1
        assert rr2.results[0].assertion == "foo"

    def test_control_mappings(self):
        results = [
            TestResult(test_name="a", nodeid="a", status="passed", soc2_controls=["CC6.1"]),
            TestResult(test_name="b", nodeid="b", status="passed", soc2_controls=["CC6.6"]),
            TestResult(test_name="c", nodeid="c", status="passed", soc2_controls=["CC6.1", "CC6.6"]),
        ]
        m = _control_mappings(results)
        assert "CC6.1" in m
        assert set(m["CC6.1"]) == {"a", "c"}
        assert set(m["CC6.6"]) == {"b", "c"}

    def test_history_append_and_read(self):
        d = tempfile.mkdtemp()
        try:
            hp = os.path.join(d, "history.jsonl")
            _append_history(hp, {"ts": "t1","id": "abc","total": 5,"passed": 4,"rate": 80})
            _append_history(hp, {"ts": "t2","id": "def","total": 5,"passed": 5,"rate": 100})
            h = _read_history(hp)
            assert len(h) == 2
            assert h[-1]["passed"] == 5
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_build_context(self):
        rr = RunReport.new()
        rr.results.append(TestResult(
            test_name="t", nodeid="t", status="passed", tenant_pair=["c1","c2"],
            soc2_controls=["CC6.1"], pattern="api_read", assertion="a", actual_status=403,
        ))
        ctx = build_context(rr)
        assert ctx["suite"] == "tenant-isolation"
        assert ctx["summary"]["total"] >= 1
        assert len(ctx["tenant_pairs"]) >= 0


class TestCliArgs:
    def test_split_no_output_json(self):
        args, out = _split_results_arg([])
        assert args == []
        assert out is None

    def test_split_with_output_json(self):
        args, out = _split_results_arg(["--output-json", "results.json", "-m", "security"])
        assert out == "results.json"
        assert args == ["-m", "security"]

    def test_split_with_equals(self):
        args, out = _split_results_arg(["--output-json=results.json", "tests/"])
        assert out == "results.json"
        assert args == ["tests/"]

    def test_forward_pytest_args(self):
        args, out = _split_results_arg(["-m", "security", "--output-json", "r.json", "tests/"])
        assert out == "r.json"
        assert args == ["-m", "security", "tests/"]


# Allow standalone run: python -m pytest tests/test_adapters.py -q