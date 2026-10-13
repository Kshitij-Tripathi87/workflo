"""Workflo AI serving API — HTTP surface over the fail-closed ModelRouter.

Three task endpoints map 1:1 onto the frozen adapter set:

  POST /v1/test_gen    -> test-gen adapter   -> WriteTestCall   + compile_check
  POST /v1/reasoning   -> reasoning adapter  -> ProposeInvariantCall + property gates
  POST /v1/reporting   -> reporting adapter  -> ReportNarrative (structured input only)

Every response carries an ``artifacts`` block (manifest identities: image
digest, base model sha256, adapter sha256s) so callers and logs can always
answer "which exact weights produced this output".

Fail-closed behavior:
  - The app refuses to start unless the artifact manifest loads and every
    digest on disk matches (ArtifactRegistry with verify_files=True).
  - Adapter discovery failures surface as HTTP 503.
  - Generation/schema/gate failures surface as HTTP 422 — a bad generation
    costs a wasted call, never a false result.

The router is injected, so tests can substitute a deterministic fake without
a GPU or a real llama-server.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from workflo_ai_integration.artifact_registry import (
    ArtifactRegistry,
    ArtifactRegistryError,
)
from workflo_ai_integration.model_router import (
    AdapterLoadError,
    GenerationValidationError,
    ModelRouter,
    RouterConfig,
    TaskType,
)

logger = logging.getLogger("workflo_ai_integration.service")

# Prompt size ceilings: upstream llama-server has n_predict=2048, and the
# adapters were trained on short structured prompts. Anything larger is a
# misuse of the API, not an edge case to forward.
MAX_SYSTEM_PROMPT_CHARS = 8_192
MAX_USER_PROMPT_CHARS = 32_768
MAX_REPORT_RESULTS_BYTES = 262_144

TASK_ENDPOINTS: dict[str, TaskType] = {
    "/v1/test_gen": "test-gen",
    "/v1/reasoning": "reasoning",
    "/v1/reporting": "reporting",
}


class TaskRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=MAX_USER_PROMPT_CHARS)
    system_prompt: str | None = Field(None, max_length=MAX_SYSTEM_PROMPT_CHARS)

    @field_validator("user_prompt", "system_prompt")
    @classmethod
    def reject_whitespace_only(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return value


class ReportRequest(BaseModel):
    results: dict[str, Any]

    model_config = {"extra": "forbid"}


def _latency_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def create_app(
    router: ModelRouter | None = None,
    registry: ArtifactRegistry | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``router`` and ``registry`` are injectable for deterministic tests.
    Production defaults: loopback ModelRouter + repo manifest, verified.
    """
    if registry is None:
        registry = ArtifactRegistry()  # verifies all digests on disk
    if router is None:
        router = ModelRouter(RouterConfig())

    app = FastAPI(
        title="Workflo AI Serving API",
        version="0.1.0",
        description="Fail-closed adapter routing over manifest-pinned GGUFs.",
    )
    app.state.router = router
    app.state.registry = registry

    # -- error mapping ------------------------------------------------------

    @app.exception_handler(AdapterLoadError)
    async def adapter_load_failed(request: Request, exc: AdapterLoadError):
        return JSONResponse(
            status_code=503,
            content={"error": "adapter_load_failed", "detail": str(exc)},
        )

    @app.exception_handler(GenerationValidationError)
    async def generation_invalid(request: Request, exc: GenerationValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "generation_validation_failed", "detail": str(exc)},
        )

    # -- endpoints ------------------------------------------------------------

    def _artifacts() -> dict[str, Any]:
        return registry.telemetry()

    def _log_telemetry(endpoint: str, latency_ms: int, status: str) -> None:
        # Structured single-line telemetry; identities only, never payloads.
        logger.info(
            "task_endpoint endpoint=%s latency_ms=%d status=%s model=%s "
            "model_sha256=%s image=%s",
            endpoint,
            latency_ms,
            status,
            registry.snapshot.model_id,
            registry.snapshot.model_sha256,
            registry.snapshot.llama_cpp_image.split("@")[-1][:16],
        )

    @app.get("/v1/health")
    def health() -> JSONResponse:
        try:
            ids = router.discover_adapters()
        except AdapterLoadError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "reason": f"adapter discovery failed: {exc}",
                    "artifacts": _artifacts(),
                },
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "adapter_ids": {task: ids[task] for task in sorted(ids)},
                "artifacts": _artifacts(),
            },
        )

    def _run_task_endpoint(endpoint: str, body: TaskRequest) -> JSONResponse:
        task = TASK_ENDPOINTS[endpoint]
        system_prompt = body.system_prompt
        if system_prompt is None:
            # Deferred import keeps dataset_sources (a training-side module)
            # out of the serving import graph for non-default paths.
            from workflo_ai_integration.service_defaults import SYSTEM_PROMPTS

            system_prompt = SYSTEM_PROMPTS[task]
        start = time.perf_counter()
        try:
            result = router.generate_for_task(task, system_prompt, body.user_prompt)
        except (AdapterLoadError, GenerationValidationError):
            _log_telemetry(endpoint, _latency_ms(start), "rejected")
            raise
        latency = _latency_ms(start)
        _log_telemetry(endpoint, latency, "ok")
        return JSONResponse(
            status_code=200,
            content={
                "task": task,
                "result": result.model_dump(),
                "artifacts": _artifacts(),
                "latency_ms": latency,
            },
        )

    @app.post("/v1/test_gen")
    def test_gen(body: TaskRequest) -> JSONResponse:
        return _run_task_endpoint("/v1/test_gen", body)

    @app.post("/v1/reasoning")
    def reasoning(body: TaskRequest) -> JSONResponse:
        return _run_task_endpoint("/v1/reasoning", body)

    @app.post("/v1/reporting")
    def reporting(body: ReportRequest) -> JSONResponse:
        endpoint = "/v1/reporting"
        import json as _json

        if len(_json.dumps(body.results)) > MAX_REPORT_RESULTS_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "results_too_large",
                    "detail": f"results must serialize to <= {MAX_REPORT_RESULTS_BYTES} bytes",
                },
            )
        start = time.perf_counter()
        try:
            result = router.generate_report(body.results)
        except (AdapterLoadError, GenerationValidationError):
            _log_telemetry(endpoint, _latency_ms(start), "rejected")
            raise
        latency = _latency_ms(start)
        _log_telemetry(endpoint, latency, "ok")
        return JSONResponse(
            status_code=200,
            content={
                "task": "reporting",
                "result": result.model_dump(),
                "artifacts": _artifacts(),
                "latency_ms": latency,
            },
        )

    return app


__all__ = [
    "ArtifactRegistryError",
    "ReportRequest",
    "TaskRequest",
    "create_app",
]
