"""JARVIS OS - Phase 27.C HealthProbe Tests.

Validates heartbeat registration, time.monotonic() timeout calculations,
and component health transitions.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.observability.dto import ComponentStatus
from core.observability.health_probe import HealthProbe


@pytest.fixture
def probe() -> HealthProbe:
    # Set timeout to 0.1s for fast tests
    return HealthProbe(heartbeat_timeout_seconds=0.1)


class TestHealthProbe:
    """HealthProbe verification suite (Architect constraint C4: monotonic clock)."""

    @pytest.mark.asyncio
    async def test_emit_heartbeat_registers_component(self, probe: HealthProbe) -> None:
        """emit_heartbeat registers the component and marks it ONLINE."""
        await probe.emit_heartbeat("AgentService")

        statuses = await probe.get_health_status()
        assert "AgentService" in statuses
        assert statuses["AgentService"] == ComponentStatus.ONLINE.value

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_transitions_to_offline(
        self, probe: HealthProbe
    ) -> None:
        """If elapsed monotonic time > timeout, status transitions to OFFLINE."""
        await probe.emit_heartbeat("AgentService")
        # Wait for timeout (0.1s)
        await asyncio.sleep(0.12)

        statuses = await probe.get_health_status()
        assert statuses["AgentService"] == ComponentStatus.OFFLINE.value

    @pytest.mark.asyncio
    async def test_get_health_records(self, probe: HealthProbe) -> None:
        """get_health_records returns full ComponentHealthRecord objects."""
        meta = {"load": 0.5}
        await probe.emit_heartbeat("AgentService", metadata=meta)

        records = await probe.get_health_records()
        assert len(records) == 1
        assert records[0].component_id == "AgentService"
        assert records[0].status == ComponentStatus.ONLINE
        assert records[0].metadata == meta
        assert records[0].last_heartbeat is not None

    @pytest.mark.asyncio
    async def test_multiple_components(self, probe: HealthProbe) -> None:
        """HealthProbe tracks multiple components independently."""
        await probe.emit_heartbeat("CompA")
        await asyncio.sleep(0.05)
        await probe.emit_heartbeat("CompB")

        statuses = await probe.get_health_status()
        assert statuses["CompA"] == ComponentStatus.ONLINE.value
        assert statuses["CompB"] == ComponentStatus.ONLINE.value

        # Wait until CompA times out but CompB is still online
        # CompA timeout is at 0.1s since its creation (started at t=0, so timeout at t=0.1)
        # CompB started at t=0.05, timeout at t=0.15
        # Wait to reach t=0.11
        await asyncio.sleep(0.07)

        statuses2 = await probe.get_health_status()
        assert statuses2["CompA"] == ComponentStatus.OFFLINE.value
        assert statuses2["CompB"] == ComponentStatus.ONLINE.value

    @pytest.mark.asyncio
    async def test_monotonic_clock_used_internally(self, probe: HealthProbe) -> None:
        """Verify time.monotonic is used to calculate elapsed time."""
        start = time.monotonic()
        await probe.emit_heartbeat("Comp")

        # Retrieve internal stored value
        stored_monotonic = probe._heartbeats["Comp"][0]
        assert stored_monotonic >= start
        assert stored_monotonic <= time.monotonic()
