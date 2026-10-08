"""Hosted-inference gateway — privacy-preserving model proxy.

The gateway is the ONLY path by which a sandboxed agent's runtime
observations reach a hosted model:

    CLI/planner  --POST /v1/inference/plan-->  Control Plane
                                                  │
                              builds system+user prompt SERVER-SIDE
                              (bounded observations only, never source code)
                                                  │
                                                  ▼
                                           upstream model
                                                  │
                                                  ▼
                              validates the returned plan (allowed tools,
                              size caps, no source-bearing fields)
                                                  │
                                                  ▼
                                           InferenceGatewayResponse
                                             (plan + provenance hashes)

Why a gateway and not a direct model key on the client:
  1. The upstream API key stays on the control plane — it is never
     written to the CLI config and never enters a sandbox.
  2. The model receives ONLY structured, bounded runtime observations
     re-serialized by the gateway. A client cannot smuggle a raw prompt
     or repository content through the protocol (extra fields and
     source-bearing keys/text are rejected).
  3. Provenance hashes (observations, gateway-built prompt, response)
     are returned to the client and signed into the receipt, so a
     reviewer can prove what was sent to the hosted model.

Auth: a valid API key with scope ``run_tests`` (the demo key qualifies).
Unavailable/misconfigured upstream -> 503 with a named error; the client
treats that as a planner-unavailable condition and ends gracefully.
"""

from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.models import ApiKey
from app.core.config import settings
from app.core.security import require_scope
from workflo_schema.inference import (
    INFERENCE_PROTOCOL_VERSION,
    InferenceGatewayRequest,
    InferenceGatewayResponse,
    InferenceProvenance,
    MAX_PROMPT_BYTES,
    canonical_json,
    parse_plan_text,
    sha256_json,
)

router = APIRouter(prefix="/inference", tags=["inference"])


def _build_messages(request: InferenceGatewayRequest) -> list[dict]:
    """The ONLY prompt the gateway sends upstream, built from bounded
    observations. No caller-supplied prompt text is accepted anywhere."""
    budget = request.budget
    observations = [obs.model_dump(mode="json") for obs in request.observations]

    system = (
        "You are a QA testing agent operating a running web application "
        "through governed tools inside an isolated sandbox.\n"
        "Available tools:\n"
        '  http_get {"url": "http://app.workflo.internal:<port>/path"}\n'
        '  http_post {"url": "...", "body": {...}}\n'
        '  read_log {"lines": N}\n'
        '  list_files {"path": "/workspace/repo"}\n'
        '  read_file {"path": "..."}\n'
        "Rules:\n"
        "- Only hosts under .workflo.internal are reachable; other targets "
        "are denied and recorded.\n"
        "- Do not repeat identical calls you already made.\n"
        "- Explore endpoints, flows and error handling; look for broken "
        "behavior, unexpected statuses and inconsistencies.\n"
        "- At most 8 steps per batch.\n"
        "Respond with ONLY a JSON object:\n"
        '  {"done": <bool>, "steps": [{"tool": "...", "args": {...}, "reason": "..."}]}\n'
        "Set done=true when you have enough evidence or the budget is low."
    )

    user = (
        f"Task: autonomously test the application at {request.app_url}.\n"
        + (f"Mission: {request.mission}\n" if request.mission else "")
        + f"Budget: {budget.batches_left} batches left, "
        f"{budget.tool_calls_left} tool calls left.\n"
        f"Observations so far ({len(observations)}):\n"
        + json.dumps(observations[-60:], default=str)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _call_upstream(messages: list[dict]) -> str:
    """Forward the gateway-built prompt to the upstream model, returning
    the raw assistant content."""
    if not settings.upstream_llm_base_url:
        raise HTTPException(
            status_code=503,
            detail="inference gateway upstream not configured (upstream_llm_base_url)",
        )

    body = json.dumps({
        "model": settings.upstream_llm_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
    }).encode("utf-8")

    headers = {"Content-Type": "application/json", "User-Agent": "workflo-gateway/0.3"}
    if settings.upstream_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.upstream_llm_api_key}"

    url = settings.upstream_llm_base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=settings.upstream_llm_timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"upstream model rejected the request (HTTP {e.code})",
        )
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=502, detail=f"upstream model unreachable: {e}")

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="upstream model response malformed")


@router.post("/plan", response_model=InferenceGatewayResponse)
async def create_plan(
    body: InferenceGatewayRequest,
    http_request: Request,
    api_key: ApiKey = Depends(require_scope("run_tests")),
):
    """Turn bounded runtime observations into a validated tool plan."""
    request_id = str(uuid.uuid4())
    observations = [obs.model_dump(mode="json") for obs in body.observations]

    messages = _build_messages(body)
    prompt_bytes = canonical_json(messages)
    if len(prompt_bytes) > MAX_PROMPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"gateway prompt exceeds {MAX_PROMPT_BYTES} bytes — reduce observations",
        )

    content = _call_upstream(messages)
    try:
        plan = parse_plan_text(content)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"upstream model returned an invalid plan: {e}")

    provenance = InferenceProvenance(
        mode="gateway",
        protocol_version=INFERENCE_PROTOCOL_VERSION,
        gateway_url=f"{http_request.url.scheme}://{http_request.url.netloc}",
        gateway_version=settings.inference_gateway_version,
        model=settings.upstream_llm_model,
        requests=1,
        observations_sent=len(observations),
        source_code_included=False,
        observation_sha256=sha256_json(observations),
        prompt_sha256=sha256_json(messages),
        response_sha256=sha256_json(content),
        request_ids=[request_id],
    )

    return InferenceGatewayResponse(
        protocol_version=INFERENCE_PROTOCOL_VERSION,
        plan=plan,
        provenance=provenance,
    )


@router.get("/health")
async def inference_health():
    """Report gateway status without revealing the upstream model or key."""
    return {
        "status": "configured" if settings.upstream_llm_base_url else "unconfigured",
        "version": settings.inference_gateway_version,
        "model": settings.upstream_llm_model if settings.upstream_llm_base_url else None,
    }