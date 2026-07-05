"""JARVIS OS - Mission Checkpoint and Rollback Tests."""

from typing import Any, Dict

import pytest
from sqlalchemy import select

from core.runtime.mission_models import MissionModel


@pytest.mark.asyncio
async def test_checkpoints_and_rollback(setup_mission_env: Dict[str, Any]) -> None:
    """Verify checkpoints can be written and a mission rolled back to them."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # 1. Create and Start Mission
    res = await mission_mgr.create_mission(goal="Rolling test", budget_limit=10.0)
    mission_id = res["mission_id"]
    await mission_mgr.start_mission(mission_id)

    # 2. Write two checkpoints
    cp1 = await mission_mgr.create_checkpoint(
        mission_id, step_index=1, state_data={"file": "a.txt"}
    )
    cp2 = await mission_mgr.create_checkpoint(
        mission_id, step_index=2, state_data={"file": "b.txt"}
    )

    assert cp1["step_index"] == 1
    assert cp2["step_index"] == 2

    # 3. Verify step index rollback
    rollback_res = await mission_mgr.rollback_to_checkpoint(
        mission_id, cp1["checkpoint_id"]
    )
    assert rollback_res["status"] == "PAUSED"
    assert rollback_res["current_step"] == 1

    # 4. Check DB state matches rollback
    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
        res_db = await session.execute(stmt)
        mission = res_db.scalar_one()
        assert mission.current_step == 1
        assert mission.status == "PAUSED"
