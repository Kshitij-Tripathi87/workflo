"""Observability middleware: request IDs, latency metrics, error capture."""

import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import logger
from app.core.metrics import REQUEST_DURATION, REQUESTS_TOTAL
from app.core.exceptions import CortexError


def _safe_path(path: str) -> str:
    """Collapse path segments with high cardinality to keep Prometheus label
    cardinality bounded. URNs and long IDs become ":ulum:".
    """
    parts = path.split("?")[0].split("/")
    out = []
    for p in parts:
        # Long alnum-looking segments (URNs, hashes, ids) -> placeholder
        if len(p) > 32:
            out.append(":ulum:")
        elif p and all(c.isalnum() or c in "-_" for c in p) and len(p) > 16:
            out.append(":ulum:")
        else:
            out.append(p)
    return "/".join(out)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID and binds it to the log context."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        logger.bind(request_id=request_id, path=request.url.path, method=request.method).info("request.start")

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records Prometheus metrics for each request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            duration = time.perf_counter() - start
            path_label = _safe_path(request.url.path)
            REQUESTS_TOTAL.labels(method=request.method, path=path_label, status=status).inc()
            REQUEST_DURATION.labels(method=request.method, path=path_label).observe(duration)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Converts CortexError exceptions into structured JSON responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except CortexError as exc:
            logger.bind(
                error=exc.code,
                message=exc.message,
                request_id=getattr(request.state, "request_id", None),
            ).error("request.error")
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.bind(
                error="INTERNAL_ERROR",
                message=str(exc),
                request_id=getattr(request.state, "request_id", None),
            ).exception("request.unhandled_error")
            return JSONResponse(
                status_code=500,
                content={"error": "INTERNAL_ERROR", "message": "Internal server error"},
            )
