"""JARVIS OS - Mission Manager Tests."""

from typing import Any, Dict

import pytest


@pytest.mark.asyncio
async def test_mission_lifecycle(setup_mission_env: Dict[str, Any]) -> None:
    """Verify standard mission creation, plan generation, and lifecycle steps."""
    mission_mgr = setup_mission_env["mission_mgr"]

    # 1. Create Mission
    res = await mission_mgr.create_mission(
        goal="Test goal execution", budget_limit=100.0
    )
    assert res["status"] == "CREATED"
    assert res["goal"] == "Test goal execution"
    assert res["budget_limit"] == 100.0
    mission_id = res["mission_id"]

    # 2. Start Mission
    start_res = await mission_mgr.start_mission(mission_id)
    assert start_res["status"] == "RUNNING"
    assert len(start_res["steps"]) == 3

    # 3. Pause Mission
    pause_res = await mission_mgr.pause_mission(mission_id)
    assert pause_res["status"] == "PAUSED"

    # 4. Resume Mission
    resume_res = await mission_mgr.resume_mission(mission_id)
    assert resume_res["status"] == "RUNNING"

    # 5. Cancel Mission
    cancel_res = await mission_mgr.cancel_mission(mission_id)
    assert cancel_res["status"] == "CANCELLED"
