#!/usr/bin/env python3
"""Smoke-test the deployed Workflo observation-only inference gateway.

Stores only response metadata, not prompts, observations, or the proposed tool plan.
The source-code rejection probe must be rejected before it reaches the upstream model.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
            "User-Agent": "workflo-p4-gateway-smoke/1.0",
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
            parsed = {"detail": "non-JSON HTTP error response"}
        return exc.code, parsed, time.monotonic() - started


def main() -> int:
    base_url = os.environ.get("WORKFLO_GATEWAY_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get("WORKFLO_GATEWAY_API_KEY", "").strip()
    expected_model = os.environ.get("WORKFLO_MODEL_NAME", "").strip()
    output = os.environ.get("WORKFLO_GATEWAY_SMOKE_OUT", "gateway-smoke.json")
    if not base_url or not api_key or not expected_model:
        print("Required env vars: WORKFLO_GATEWAY_BASE_URL, WORKFLO_GATEWAY_API_KEY, WORKFLO_MODEL_NAME", file=sys.stderr)
        return 2
    if not base_url.startswith("https://"):
        print("WORKFLO_GATEWAY_BASE_URL must use HTTPS", file=sys.stderr)
        return 2

    endpoint = base_url + "/v1/inference/plan"
    valid_request = {
        "protocol_version": 1,
        "session_id": "p4-release-smoke",
        "app_url": "http://app.workflo.internal:3000",
        "mission": "Check whether the health endpoint responds correctly.",
        "budget": {"batches_left": 1, "tool_calls_left": 2},
        "observations": [
            {"tool": "http_get", "ok": True, "description": "GET /health", "detail": "HTTP 200"},
        ],
    }

    status, response, elapsed = post_json(endpoint, valid_request, api_key)
    if status != 200 or not isinstance(response, dict):
        print(f"Gateway valid-request smoke failed: HTTP {status}; response body suppressed", file=sys.stderr)
        return 1
    provenance = response.get("provenance")
    if not isinstance(provenance, dict):
        print("Gateway response lacks provenance", file=sys.stderr)
        return 1
    if provenance.get("source_code_included") is not False:
        print("Privacy invariant failed: source_code_included is not false", file=sys.stderr)
        return 1
    if provenance.get("model") != expected_model:
        print("Gateway model identifier does not match WORKFLO_MODEL_NAME", file=sys.stderr)
        return 1
    if not provenance.get("request_ids"):
        print("Gateway provenance has no request IDs", file=sys.stderr)
        return 1
    for key in ("observation_sha256", "prompt_sha256", "response_sha256"):
        value = provenance.get(key)
        if not isinstance(value, str) or len(value) != 64:
            print("Gateway provenance has a missing or malformed hash", file=sys.stderr)
            return 1

    invalid_request = dict(valid_request)
    invalid_request["source_code"] = "WORKFLO_P4_SOURCE_CANARY_DO_NOT_FORWARD"
    reject_status, reject_response, reject_elapsed = post_json(endpoint, invalid_request, api_key)
    rejection_text = json.dumps(reject_response, sort_keys=True)
    if reject_status != 422:
        print(f"Privacy negative test failed: expected HTTP 422 for source-bearing field, received {reject_status}", file=sys.stderr)
        return 1
    if "WORKFLO_P4_SOURCE_CANARY_DO_NOT_FORWARD" in rejection_text:
        print("Privacy negative test failed: error response echoed the source canary", file=sys.stderr)
        return 1

    report = {
        "valid_request": {
            "http_status": status,
            "elapsed_seconds": round(elapsed, 4),
            "model": provenance.get("model"),
            "mode": provenance.get("mode"),
            "source_code_included": provenance.get("source_code_included"),
            "request_ids": provenance.get("request_ids"),
            "observation_sha256": provenance.get("observation_sha256"),
            "prompt_sha256": provenance.get("prompt_sha256"),
            "response_sha256": provenance.get("response_sha256"),
            "input_tokens": provenance.get("input_tokens"),
            "output_tokens": provenance.get("output_tokens"),
            "inference_seconds": provenance.get("inference_seconds"),
        },
        "source_rejection": {
            "http_status": reject_status,
            "elapsed_seconds": round(reject_elapsed, 4),
            "passed": True,
        },
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Gateway smoke passed: valid request HTTP {status}; source-bearing request rejected HTTP {reject_status}.")
    print(f"Redacted metadata report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
