"""Judge tests — deterministic finding confirmation over governed records."""

from __future__ import annotations

from sandbox_runtime.judge import judge_findings


def _http_record(seq, method_tool, url, status, ok=True, denied=False,
                 error=None):
    summary = {"ok": ok, "status": status}
    if error:
        summary["error"] = error
    return {
        "seq": seq,
        "tool": method_tool,
        "args": {"url": url},
        "denied": denied,
        "ok": ok,
        "result_summary": summary,
    }


def test_single_failure_is_reported_not_confirmed():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/health", 200),
        _http_record(2, "http_post", "http://app.workflo.internal:3000/checkout", 500),
    ]
    report = judge_findings(records)
    assert report.hypotheses == 1
    assert report.confirmed == 0
    assert report.reported == 1
    finding = report.findings[0]
    assert finding["status"] == "reported"
    assert "checkout" in finding["title"]


def test_repeated_failure_with_healthy_control_is_confirmed():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_post", "http://app.workflo.internal:3000/checkout", 500),
        _http_record(3, "http_get", "http://app.workflo.internal:3000/products", 200),
        _http_record(4, "http_post", "http://app.workflo.internal:3000/checkout", 500),
    ]
    report = judge_findings(records)
    assert report.confirmed == 1
    finding = report.findings[0]
    assert finding["status"] == "confirmed"
    assert finding["severity"] == "medium"
    assert finding["reproduction"]["observed_failures"] == 2
    assert finding["reproduction"]["attempt_seqs"] == [2, 4]


def test_repeated_failure_without_control_stays_reported():
    records = [
        _http_record(1, "http_post", "http://app.workflo.internal:3000/checkout", 500),
        _http_record(2, "http_post", "http://app.workflo.internal:3000/checkout", 500),
    ]
    report = judge_findings(records)
    assert report.confirmed == 0
    assert report.reported == 1


def test_denied_calls_never_count_as_evidence():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_get", "http://evil.example.com/x", None,
                     denied=True, ok=False, error="denied"),
        _http_record(3, "http_get", "http://evil.example.com/x", None,
                     denied=True, ok=False, error="denied"),
    ]
    report = judge_findings(records)
    assert report.findings == []


def test_no_failures_no_findings():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_get", "http://app.workflo.internal:3000/health", 200),
    ]
    report = judge_findings(records)
    assert report.findings == []


def test_connection_error_counts_as_failure():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_get", "http://app.workflo.internal:3000/api/x", None,
                     error="ConnectionRefusedError"),
        _http_record(3, "http_get", "http://app.workflo.internal:3000/api/x", None,
                     error="ConnectionRefusedError"),
    ]
    report = judge_findings(records)
    assert report.confirmed == 1
    assert report.findings[0]["reproduction"]["failure_class"] == "conn_error"


def test_evidence_refs_use_ledger_event_ids_when_given():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_post", "http://app.workflo.internal:3000/pay", 500),
        _http_record(3, "http_post", "http://app.workflo.internal:3000/pay", 500),
    ]
    event_ids = {1: "evt_00000001", 2: "evt_00000002", 3: "evt_00000003"}
    report = judge_findings(records, event_ids)
    finding = report.findings[0]
    assert finding["status"] == "confirmed"
    assert finding["evidence_refs"] == ["evt_00000002", "evt_00000003"]


def test_finding_id_is_stable_across_runs():
    def records(offset):
        return [
            _http_record(offset, "http_get", "http://app.workflo.internal:3000/", 200),
            _http_record(offset + 1, "http_post",
                         "http://app.workflo.internal:3000/checkout", 500),
            _http_record(offset + 2, "http_post",
                         "http://app.workflo.internal:3000/checkout", 500),
        ]

    a = judge_findings(records(10)).findings[0]
    b = judge_findings(records(60)).findings[0]
    assert a["finding_id"] == b["finding_id"]
    assert a["finding_id"].startswith("wf-fnd-")


def test_4xx_is_not_a_finding():
    records = [
        _http_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _http_record(2, "http_get", "http://app.workflo.internal:3000/missing", 404),
        _http_record(3, "http_get", "http://app.workflo.internal:3000/missing", 404),
    ]
    report = judge_findings(records)
    assert report.findings == []


def test_gateway_jsonl_encoded_args_are_unwrapped():
    """The on-disk records store args JSON-encoded (ToolGateway bounding);
    the judge must still extract the real path."""
    def encoded(seq, tool, url, status):
        import json as _json
        return {
            "seq": seq, "tool": tool,
            "args": {"url": _json.dumps(url)},
            "denied": False, "ok": True,
            "result_summary": {"ok": True, "status": status},
        }

    records = [
        encoded(1, "http_get", "http://app.workflo.internal:3000/", 200),
        encoded(2, "http_post", "http://app.workflo.internal:3000/checkout", 500),
        encoded(3, "http_post", "http://app.workflo.internal:3000/checkout", 500),
    ]
    report = judge_findings(records)
    assert report.confirmed == 1
    assert report.findings[0]["title"] == "POST /checkout fails (HTTP 500)"
