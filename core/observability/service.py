"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

ObservabilityService — main composition root and event bus orchestrator.

Architect constraints incorporated:
- C2: CostGovernor and ExecutionTracer processing runs fire-and-forget in background without blocking the event bus.
- C4: Monotonic clocks for timing.
- Q1: Subscribes to existing llm.response events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.interfaces import EventBusInterface, InterAgentMessage, LifecycleInterface
from core.observability.broadcaster_interface import BaseTelemetryBroadcaster
from core.observability.cost_governor import CostGovernor
from core.observability.dto import SpanStatus, TelemetryEnvelope
from core.observability.health_probe import HealthProbe
from core.observability.span_repository import SpanRepository
from core.observability.tracer import ExecutionTracer

logger = logging.getLogger("jarvis.core.observability.service")


class ObservabilityService(LifecycleInterface):
    """Integrates tracer, cost governor, health probe, and broadcaster with the event bus.

    Implements LifecycleInterface to sequence boot and shutdown.
    """

    def __init__(
        self,
        event_bus: EventBusInterface,
        span_repo: SpanRepository,
        cost_gov: CostGovernor,
        health_probe: HealthProbe,
        broadcaster: BaseTelemetryBroadcaster,
    ) -> None:
        self._event_bus = event_bus
        self.span_repo = span_repo
        self.cost_gov = cost_gov
        self.health_probe = health_probe
        self.broadcaster = broadcaster
        self.tracer = ExecutionTracer(span_repo)

        self._subscription_ids: List[str] = []
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._telemetry_task: Optional[asyncio.Task[None]] = None
        self._running = False

        # Internal event-driven metrics tracking to avoid importing frozen components
        self._active_agents_count = 0
        self._queued_tasks_count = 0
        self._completed_tasks_count = 0
        self._failed_tasks_count = 0

    # ── LifecycleInterface implementation ─────────────────────────────

    async def initialize(self) -> None:
        """Initialize routes context and prepare dependencies."""
        logger.info("ObservabilityService initialized successfully.")

    async def start(self) -> None:
        """Subscribe to events and spawn monitoring loop coroutines."""
        if self._running:
            return
        self._running = True

        # Subscribe to Event Bus topics (Architect Q1: llm.response subscription)
        topics = {
            "swarm.task.started": self._on_task_started,
            "swarm.task.completed": self._on_task_completed,
            "swarm.task.failed": self._on_task_failed,
            "llm.response": self._on_llm_response,
            "kernel.heartbeat": self._on_kernel_heartbeat,
        }

        for topic, handler in topics.items():
            sub_id = await self._event_bus.subscribe(topic, handler)
            self._subscription_ids.append(sub_id)

        # Spawn background tickers
        self._heartbeat_task = asyncio.create_task(self._run_heartbeat_loop())
        self._telemetry_task = asyncio.create_task(self._run_telemetry_loop())

        logger.info("ObservabilityService started. Subscribed to %d topics.", len(topics))

    async def stop(self) -> None:
        """Clean up subscribers and stop coroutines."""
        if not self._running:
            return
        self._running = False

        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._telemetry_task:
            self._telemetry_task.cancel()

        self._subscription_ids.clear()
        logger.info("ObservabilityService stopped.")

    async def shutdown(self) -> None:
        """Finalize teardown."""
        logger.info("ObservabilityService shutdown complete.")

    # ── Event Bus Callbacks ──────────────────────────────────────────

    async def _on_task_started(self, msg: InterAgentMessage) -> None:
        """Handle task started event."""
        self._queued_tasks_count = max(0, self._queued_tasks_count - 1)
        # Delegate to tracer (non-blocking async wrapper inside tracer)
        await self.tracer.on_task_event(
            msg.body, operation=msg.body.get("operation", "task.run"), status=SpanStatus.STARTED
        )

    async def _on_task_completed(self, msg: InterAgentMessage) -> None:
        """Handle task completed event."""
        self._completed_tasks_count += 1
        await self.tracer.on_task_event(
            msg.body, operation=msg.body.get("operation", "task.run"), status=SpanStatus.COMPLETED
        )

    async def _on_task_failed(self, msg: InterAgentMessage) -> None:
        """Handle task failed event."""
        self._failed_tasks_count += 1
        await self.tracer.on_task_event(
            msg.body, operation=msg.body.get("operation", "task.run"), status=SpanStatus.FAILED
        )

    async def _on_llm_response(self, msg: InterAgentMessage) -> None:
        """Handle LLM response and update cost governor statistics (Architect Q1)."""
        await self.cost_gov.on_llm_response_event(msg.body)

    async def _on_kernel_heartbeat(self, msg: InterAgentMessage) -> None:
        """Handle system heartbeats."""
        component_id = msg.body.get("component_id", "Unknown")
        await self.health_probe.emit_heartbeat(component_id, metadata=msg.body.get("metadata"))

    # ── Background Loops ─────────────────────────────────────────────

    async def _run_heartbeat_loop(self) -> None:
        """Emit component heartbeat every 10 seconds per standard."""
        while self._running:
            try:
                # Local heartbeat
                await self.health_probe.emit_heartbeat("ObservabilityService")

                # Publish heartbeat message to event bus
                heartbeat_msg = InterAgentMessage(
                    sender="ObservabilityService",
                    receiver="All",
                    action="heartbeat",
                    body={"component_id": "ObservabilityService", "timestamp": str(datetime.now(timezone.utc))},
                )
                await self._event_bus.publish("kernel.heartbeat", heartbeat_msg)
            except Exception as exc:
                logger.warning("Failed to emit/publish heartbeat: %s", exc)
            await asyncio.sleep(10.0)

    async def _run_telemetry_loop(self) -> None:
        """Assemble and broadcast TelemetryEnvelope every 2 seconds."""
        while self._running:
            try:
                # Fetch daily summary
                summary = await self.cost_gov.get_daily_summary()
                health_statuses = await self.health_probe.get_health_status()
                recent_spans = self.tracer.get_recent_summaries()

                # Determine active agent count (ONLINE count)
                active_agents = sum(1 for status in health_statuses.values() if status == "ONLINE")

                envelope = TelemetryEnvelope(
                    active_agents=active_agents,
                    queued_tasks=self._queued_tasks_count,
                    completed_tasks=self._completed_tasks_count,
                    failed_tasks=self._failed_tasks_count,
                    cost_today_usd=summary.daily_cost_usd,
                    cost_month_usd=summary.monthly_cost_usd,
                    cost_tier=summary.tier.value,
                    component_health=health_statuses,
                    recent_spans=recent_spans,
                )
                await self.broadcaster.broadcast(envelope)
            except Exception as exc:
                logger.warning("Telemetry loop broadcast failed: %s", exc)
            await asyncio.sleep(2.0)
