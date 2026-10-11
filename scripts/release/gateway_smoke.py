#!/usr/bin/env python3
"""Exercise protected gateway auth, privacy, and redaction controls.

The retained report contains only statuses, hashes, counts, timings, and
outcomes. Request payloads, response plans, credentials, endpoints, and canary
values are inspected in memory and never written to evidence.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def post_json(url: str, payload: dict, api_key: str, timeout: float = 90.0):
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Key": api_key,
            "User-Agent": "workflo-p4-gateway-smoke/2.0",
        },
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024)
            return response.status, json.loads(raw), time.monotonic() - started
    except HTTPError as exc:
        raw = exc.read(8192).decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"detail": "non_json_http_error"}
        return exc.code, parsed, time.monotonic() - started
    except (URLError, OSError, TimeoutError):
        return 0, {"detail": "transport_error"}, time.monotonic() - started


def _base_request() -> dict:
    return {
        "protocol_version": 1,
        "session_id": "p4-release-smoke",
        "app_url": "http://app.workflo.internal:3000",
        "mission": "Check whether the health endpoint responds correctly.",
        "budget": {"batches_left": 1, "tool_calls_left": 2},
        "observations": [
            {
                "tool": "http_get",
                "ok": True,
                "description": "GET /health",
                "detail": "HTTP 200",
            },
        ],
    }


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    base_url = os.environ.get("WORKFLO_GATEWAY_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get("WORKFLO_GATEWAY_API_KEY", "").strip()
    expected_model = os.environ.get("WORKFLO_MODEL_NAME", "").strip()
    output = Path(os.environ.get("WORKFLO_GATEWAY_SMOKE_OUT", "gateway-smoke.json"))
    report: dict = {
        "passed": False,
        "authorization_rejection": {"passed": False},
        "wrong_key_rejection": {"passed": False},
        "valid_request": {"passed": False},
        "redaction": {"passed": False},
        "source_rejection": {"passed": False, "cases": 0},
        "failure_class": None,
    }

    def fail(failure_class: str, message: str) -> int:
        report["failure_class"] = failure_class
        _write_report(output, report)
        print(message, file=sys.stderr)
        return 1

    if not base_url or not api_key or not expected_model:
        return fail("configuration", "Required protected gateway configuration is missing")
    if not base_url.startswith("https://"):
        return fail("configuration", "WORKFLO_GATEWAY_BASE_URL must use HTTPS")

    endpoint = base_url + "/v1/inference/plan"
    valid_request = _base_request()

    missing_status, _, missing_elapsed = post_json(endpoint, valid_request, "")
    report["authorization_rejection"] = {
        "http_status": missing_status,
        "elapsed_seconds": round(missing_elapsed, 4),
        "passed": missing_status in (401, 403),
    }
    if missing_status not in (401, 403):
        return fail("missing_key_accepted", "Missing-key authorization rejection failed")

    wrong_status, _, wrong_elapsed = post_json(
        endpoint, valid_request, "WORKFLO-INTENTIONALLY-INVALID-P4-KEY"
    )
    report["wrong_key_rejection"] = {
        "http_status": wrong_status,
        "elapsed_seconds": round(wrong_elapsed, 4),
        "passed": wrong_status in (401, 403),
    }
    if wrong_status not in (401, 403):
        return fail("wrong_key_accepted", "Wrong-key authorization rejection failed")

    status, response, elapsed = post_json(endpoint, valid_request, api_key)
    if status != 200 or not isinstance(response, dict):
        return fail("valid_request_rejected", "Gateway valid-request smoke failed")
    provenance = response.get("provenance")
    if not isinstance(provenance, dict):
        return fail("provenance_missing", "Gateway response lacks provenance")
    if provenance.get("source_code_included") is not False:
        return fail("source_scope_invalid", "Gateway source-code privacy invariant failed")
    if provenance.get("model") != expected_model:
        return fail("model_mismatch", "Gateway model identifier mismatch")
    request_ids = provenance.get("request_ids")
    if not isinstance(request_ids, list) or not request_ids:
        return fail("request_identity_missing", "Gateway request identity is missing")
    for key in ("observation_sha256", "prompt_sha256", "response_sha256"):
        if not isinstance(provenance.get(key), str) or not HEX64.fullmatch(provenance[key]):
            return fail("provenance_hash_invalid", "Gateway provenance hash is invalid")

    report["valid_request"] = {
        "passed": True,
        "http_status": status,
        "elapsed_seconds": round(elapsed, 4),
        "model": provenance.get("model"),
        "mode": provenance.get("mode"),
        "source_code_included": False,
        "request_ids": request_ids,
        "observation_sha256": provenance.get("observation_sha256"),
        "prompt_sha256": provenance.get("prompt_sha256"),
        "response_sha256": provenance.get("response_sha256"),
        "input_tokens": provenance.get("input_tokens"),
        "output_tokens": provenance.get("output_tokens"),
        "inference_seconds": provenance.get("inference_seconds"),
    }

    secret_canary = "WFSECRET-P4-DO-NOT-FORWARD-6f2ecf1b"
    redaction_request = _base_request()
    redaction_request["observations"] = [
        {
            "tool": "http_get",
            "ok": False,
            "description": "authorization outcome",
            "detail": f"HTTP 401 api_key={secret_canary}",
        }
    ]
    redaction_status, redaction_response, redaction_elapsed = post_json(
        endpoint, redaction_request, api_key
    )
    serialized_redaction = json.dumps(redaction_response, sort_keys=True)
    redaction_provenance = (
        redaction_response.get("provenance", {})
        if isinstance(redaction_response, dict)
        else {}
    )
    redactions_applied = redaction_provenance.get("redactions_applied", 0)
    redaction_passed = bool(
        redaction_status == 200
        and secret_canary not in serialized_redaction
        and isinstance(redactions_applied, int)
        and redactions_applied >= 1
    )
    report["redaction"] = {
        "passed": redaction_passed,
        "http_status": redaction_status,
        "elapsed_seconds": round(redaction_elapsed, 4),
        "redactions_applied": redactions_applied if isinstance(redactions_applied, int) else 0,
        "canary_echoed": secret_canary in serialized_redaction,
    }
    if not redaction_passed:
        return fail("redaction_unproven", "Gateway redaction probe failed")

    source_canary = "WORKFLO-P4-SOURCE-CANARY-DO-NOT-ECHO"
    top_level = _base_request()
    top_level["source_code"] = source_canary
    nested = _base_request()
    nested["observations"][0]["extra"] = {"file_content": source_canary}
    source_text = _base_request()
    source_text["observations"][0]["detail"] = (
        f"def workflo_source_canary():\n    return '{source_canary}'"
    )
    raw_prompt = _base_request()
    raw_prompt["raw_prompt"] = source_canary
    rejection_cases = (top_level, nested, source_text, raw_prompt)
    rejection_statuses: list[int] = []
    rejection_seconds = 0.0
    for request_payload in rejection_cases:
        reject_status, reject_response, reject_elapsed = post_json(
            endpoint, request_payload, api_key
        )
        rejection_statuses.append(reject_status)
        rejection_seconds += reject_elapsed
        if reject_status != 422:
            return fail("source_request_accepted", "Source-bearing request rejection failed")
        if source_canary in json.dumps(reject_response, sort_keys=True):
            return fail("source_canary_echoed", "Source rejection echoed the source canary")

    report["source_rejection"] = {
        "passed": True,
        "cases": len(rejection_cases),
        "http_status_counts": {
            str(status_code): rejection_statuses.count(status_code)
            for status_code in sorted(set(rejection_statuses))
        },
        "elapsed_seconds": round(rejection_seconds, 4),
        "canary_echoed": False,
    }
    report["passed"] = True
    _write_report(output, report)
    print(
        "Gateway acceptance passed: missing/wrong keys rejected, provenance and "
        "redaction verified, four source-bearing requests rejected."
    )
    print(f"Redacted metadata report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
