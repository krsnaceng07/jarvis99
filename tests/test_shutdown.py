"""JARVIS OS - Graceful Shutdown and Resource Cleanup Tests.

Validates that background loops, connection pools, and managers are stopped cleanly during lifecycle shutdown.
"""

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.memory.database import db_manager
from core.memory.models import Base
from core.runtime.deployment import DeploymentHealthManager


@pytest.mark.asyncio
async def test_graceful_shutdown_lifecycle_state() -> None:
    """Verify health manager changes active states and shuts down correctly during lifecycle stop."""
    settings = Settings.load_settings()

    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    health_mgr = DeploymentHealthManager(
        settings=settings,
        db_manager=db_manager,
        event_bus=event_bus,
        vault_manager=None,
        orchestrator=None,
        admin_manager=None,
    )

    await health_mgr.initialize()
    await health_mgr.start()
    assert health_mgr._active is True

    # Stop sequence
    await health_mgr.stop()
    assert health_mgr._active is False

    # Shutdown sequence
    await health_mgr.shutdown()
    assert health_mgr._active is False

    # Clean connection pools
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()
