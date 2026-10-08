"""FastAPI application entrypoint.

Wires together:
- Routers (assets, incidents, scenarios, impact, recommendations, artifacts, writeback, demo, future_search, auth)
- Middleware (CORS, request ID, metrics, error handling)
- Health/metrics endpoints
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.core.settings import settings
from app.core.logging import configure_logging, logger
from app.core.health import get_detailed_health
from app.core.startup_checks import run_startup_checks
from app.middleware.observability import (
    RequestIDMiddleware,
    MetricsMiddleware,
    ErrorHandlingMiddleware,
)
from app.middleware.auth import get_current_user
from app.core.auth import User

from app.api.assets import router as assets_router
from app.api.incidents import router as incidents_router
from app.api.scenarios import router as scenarios_router
from app.api.impact import router as impact_router
from app.api.recommendations import router as recommendations_router
from app.api.artifacts import router as artifacts_router
from app.api.writeback import router as writeback_router
from app.api.demo import router as demo_router
from app.api.future_search import router as future_search_router
from app.api.auth import router as auth_router
from app.api.autopilot import router as autopilot_router
from app.api.policy import router as policy_router
from app.api.contracts import router as contracts_router
from app.api.receipts import router as receipts_router
from app.api.compliance import router as compliance_router
from app.services.autopilot import get_autopilot


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("startup", env=settings.ENV, mock=settings.USE_MOCK_DATAHUB)
    run_startup_checks()
    # Boot the Autopilot background worker
    autopilot = get_autopilot()
    await autopilot.start()
    yield
    # Cleanup
    await autopilot.stop()
    from app.connectors.datahub.adapter import adapter

    await adapter.close()
    from app.db.session import close_engine

    await close_engine()
    logger.info("shutdown")


app = FastAPI(title="Workflo", version="0.3.0", lifespan=lifespan)

# Middleware (order matters - outermost first)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [settings.FRONTEND_URL]
        if not settings.is_dev
        else [settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public endpoints
@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.ENV}


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health report including per-connector status, uptime, and cache stats."""
    return get_detailed_health()


@app.get("/version")
async def version():
    return {"version": "0.3.0", "name": "Workflo"}


@app.get("/metrics")
async def metrics(user: User = Depends(get_current_user)):
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Register routers
app.include_router(auth_router)
app.include_router(assets_router)
app.include_router(incidents_router)
app.include_router(scenarios_router)
app.include_router(impact_router)
app.include_router(recommendations_router)
app.include_router(artifacts_router)
app.include_router(writeback_router)
app.include_router(demo_router)
app.include_router(future_search_router)
app.include_router(autopilot_router)
app.include_router(policy_router)
app.include_router(contracts_router)
app.include_router(receipts_router)
app.include_router(compliance_router)
