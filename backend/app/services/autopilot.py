"""Autopilot — context-aware backgroundworker for Cortex.

Wraps the CortexAgent and runs two distinct execution modes:

1. Manual / webhook    — `POST /autopilot/trigger` calls `execute_task`
2. Autonomous observer — `_observe_loop` polls every connector registered
   in the context store on a configurable cadence and auto-enqueues a task
   when an asset's schema/owner has drifted since the last observation.

The Autopilot never blocks the API server: `{start|stop}` are async and
the observe loop runs as a background `asyncio.Task`. The agent itself
runs inline when triggered, but the LLM calls are IO-bound so the FastAPI
event loop stays responsive.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.settings import settings
from app.models.autopilot import AutopilotStatus, AutopilotTask
from app.services.agent import CortexAgent
from app.services.context_store import ContextStore


class Autopilot:
    """Lifecycle wrapper around CortexAgent + the observer loop."""

    def __init__(
        self,
        context_store: ContextStore,
        agent: Optional[CortexAgent] = None,
    ) -> None:
        self.context_store = context_store
        self.agent = agent or CortexAgent(context_store=context_store)
        self._running = False
        self._observer_task: Optional[asyncio.Task] = None
        self._last_observation_at: Optional[datetime] = None
        self._lock = asyncio.Lock()  # serialize manual + auto tasks

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background observer loop if enabled."""
        if self._running:
            return
        self._running = True
        if settings.CORTEX_AUTOPILOT_ENABLED:
            self._observer_task = asyncio.create_task(self._observe_loop())
            # Don't await — let it run in the background
        from app.core.logging import logger
        logger.info(
            "autopilot_start",
            enabled=settings.CORTEX_AUTOPILOT_ENABLED,
            tier=settings.CORTEX_TIER,
            trial=settings.CORTEX_TRIAL_ACTIVE,
            poll_interval=settings.CORTEX_AUTOPILOT_POLL_INTERVAL,
        )

    async def stop(self) -> None:
        """Signal the observer loop to exit and wait for it."""
        self._running = False
        if self._observer_task is not None:
            self._observer_task.cancel()
            try:
                await self._observer_task
            except (asyncio.CancelledError, Exception):
                pass
            self._observer_task = None
        from app.core.logging import logger
        logger.info("autopilot_stop")

    # ------------------------------------------------------------------
    # Task execution (entry point for the API layer)
    # ------------------------------------------------------------------

    async def execute_task(self, task: AutopilotTask) -> AutopilotTask:
        """Run an AutopilotTask through the agent. Serialised by lock."""
        async with self._lock:
            # Make sure the agent knows the asset exists
            self.context_store.store_asset_state(
                asset_urn=task.asset_urn,
                connector=task.connector,
            )
            result = await self.agent.run(task)
            self.context_store.store_task(result)
            return result

    # ------------------------------------------------------------------
    # Background observer
    # ------------------------------------------------------------------

    async def _observe_loop(self) -> None:
        """Periodically poll registered assets for drift."""
        from app.core.logging import logger

        while self._running:
            try:
                await self._observe_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("autopilot_observe_failed", error=str(exc))
            self._last_observation_at = datetime.utcnow()
            await asyncio.sleep(settings.CORTEX_AUTOPILOT_POLL_INTERVAL)

    async def _observe_once(self) -> None:
        """One pass over registered assets. Detects drift → enqueue task."""
        from app.core.logging import logger
        from app.connectors import get_connector, list_connectors

        if not list_connectors():
            import app.connectors  # noqa: F401 — trigger auto-registration

        urns = self.context_store.list_registered_assets()
        if not urns:
            return

        # Group URNs by their previously stored connector so we poll each
        # connector only once per cycle.
        by_connector: Dict[str, List[str]] = {}
        for urn in urns:
            state = self.context_store.get_asset_state(urn)
            connector_name = (state or {}).get("connector", "datahub")
            by_connector.setdefault(connector_name, []).append(urn)

        for connector_name, urn_batch in by_connector.items():
            try:
                conn = get_connector(connector_name)
            except ValueError as exc:
                logger.warning("autopilot_connector_missing", connector=connector_name, error=str(exc))
                continue

            for urn in urn_batch:
                try:
                    node = await conn.get_asset(urn)
                except Exception as exc:
                    logger.warning("autopilot_get_asset_failed", urn=urn, error=str(exc))
                    continue

                changed = self.context_store.store_asset_state(
                    asset_urn=urn,
                    connector=connector_name,
                    name=node.name,
                    owner=node.owner,
                    schema_fields=node.schema_fields,
                    metadata={"kind": node.kind, "criticality": node.criticality},
                )

                if changed:
                    logger.info("autopilot_drift_detected", urn=urn)
                    task = AutopilotTask(
                        trigger_type="auto_detect",
                        asset_urn=urn,
                        connector=connector_name,
                        change={"change_type": "schema_drift"},
                        description=f"Autopilot detected schema change on {urn}",
                    )
                    # Offload without blocking the observer loop
                    asyncio.create_task(self._safe_execute(task))

    async def _safe_execute(self, task: AutopilotTask) -> None:
        try:
            await self.execute_task(task)
        except Exception as exc:
            from app.core.logging import logger
            logger.warning("autopilot_auto_task_failed", urn=task.asset_urn, error=str(exc))

    # ------------------------------------------------------------------
    # Status snapshot
    # ------------------------------------------------------------------

    def status(self) -> AutopilotStatus:
        return AutopilotStatus(
            enabled=settings.CORTEX_AUTOPILOT_ENABLED,
            running=self._running,
            tier=settings.CORTEX_TIER,
            trial_active=settings.CORTEX_TRIAL_ACTIVE,
            poll_interval_seconds=settings.CORTEX_AUTOPILOT_POLL_INTERVAL,
            registered_assets=len(self.context_store.list_registered_assets()),
            total_tasks=self.context_store.total_tasks(),
            recent_tasks=self.context_store.recent_tasks(limit=5),
            last_observation_at=self._last_observation_at,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_autopilot: Optional[Autopilot] = None


def get_autopilot() -> Autopilot:
    """Return the initialised singleton Autopilot instance."""
    global _autopilot
    if _autopilot is None:
        _autopilot = Autopilot(context_store=ContextStore())
    return _autopilot


def reset_autopilot(autopilot: Optional[Autopilot] = None) -> None:
    """Replace or clear the singleton. Used by tests."""
    global _autopilot
    _autopilot = autopilot
