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

HealthProbe — tracks component heartbeats and health states.

Architect constraints incorporated:
- C4: Uses monotonic clock (time.monotonic()) for timeout calculations.
- C2: Does not block caller.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.observability.dto import ComponentHealthRecord, ComponentStatus

logger = logging.getLogger("jarvis.core.observability.health_probe")

_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS: float = 30.0


class HealthProbe:
    """Tracks component heartbeats using monotonic timing (Architect constraint C4).

    Monotonic clocks avoid issues caused by system time shifts.
    """

    def __init__(
        self, heartbeat_timeout_seconds: float = _DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
    ) -> None:
        self._timeout = heartbeat_timeout_seconds
        # component_id -> (monotonic_timestamp, datetime_timestamp, metadata)
        self._heartbeats: Dict[
            str, tuple[float, datetime, Optional[Dict[str, Any]]]
        ] = {}

    async def emit_heartbeat(
        self, component_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register or update the heartbeat for a component.

        Uses time.monotonic() (Architect C4) and datetime.now(timezone.utc) for logs.
        """
        now_monotonic = time.monotonic()
        now_utc = datetime.now(timezone.utc)
        self._heartbeats[component_id] = (now_monotonic, now_utc, metadata)
        logger.debug("Component %s heartbeat received", component_id)

    async def get_health_status(self) -> Dict[str, str]:
        """Verify the health status of all registered components.

        Marks components OFFLINE if the last heartbeat exceeded the timeout.
        Uses time.monotonic() for comparison (Architect C4).
        """
        now = time.monotonic()
        statuses: Dict[str, str] = {}

        for comp_id, (last_monotonic, _, _) in self._heartbeats.items():
            elapsed = now - last_monotonic
            if elapsed > self._timeout:
                statuses[comp_id] = ComponentStatus.OFFLINE.value
            else:
                statuses[comp_id] = ComponentStatus.ONLINE.value

        return statuses

    async def get_health_records(self) -> list[ComponentHealthRecord]:
        """Return full health records for all components.

        Uses time.monotonic() for health status calculation (Architect C4).
        """
        now = time.monotonic()
        records: list[ComponentHealthRecord] = []

        for comp_id, (last_monotonic, last_utc, metadata) in self._heartbeats.items():
            elapsed = now - last_monotonic
            status = (
                ComponentStatus.OFFLINE
                if elapsed > self._timeout
                else ComponentStatus.ONLINE
            )

            records.append(
                ComponentHealthRecord(
                    component_id=comp_id,
                    status=status,
                    last_heartbeat=last_utc,
                    metadata=metadata,
                )
            )

        return records
