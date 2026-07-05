"""JARVIS OS - Mission Recovery and Automatic Resumption Tests."""

from typing import Any, Dict

import pytest

from core.runtime.mission import MissionManager


@pytest.mark.asyncio
async def test_automatic_recovery(setup_mission_env: Dict[str, Any]) -> None:
    """Verify that a running mission is automatically recovered on manager startup."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]
    settings = mission_mgr.settings
    event_bus = mission_mgr.event_bus

    # 1. Create and Start Mission (Status = RUNNING)
    res = await mission_mgr.create_mission(goal="Recovery simulation goal")
    mission_id = res["mission_id"]
    await mission_mgr.start_mission(mission_id)

    # Verify task is currently active
    assert mission_id in mission_mgr._running_tasks

    # 2. Shutdown the manager (simulate crash / reboot)
    await mission_mgr.stop()

    # Verify active tasks are cleaned up
    assert mission_id not in mission_mgr._running_tasks

    # 3. Instantiate and start a new MissionManager instance on the same DB
    new_manager = MissionManager(
        settings=settings,
        db_manager=db_manager,
        event_bus=event_bus,
        vault_manager=None,
        orchestrator=None,
    )
    await new_manager.initialize()
    await new_manager.start()

    # 4. Verify the mission was recovered and is running again in the new manager
    assert mission_id in new_manager._running_tasks

    # Cleanup new manager
    await new_manager.stop()
    await new_manager.shutdown()
