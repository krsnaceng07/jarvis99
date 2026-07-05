"""JARVIS OS - Multi-Agent Mission Coordination Tests."""

import asyncio
from typing import Any, Dict

import pytest
from sqlalchemy import select

from core.runtime.mission_models import MissionModel, MissionTimelineModel


@pytest.mark.asyncio
async def test_multi_agent_coordination(setup_mission_env: Dict[str, Any]) -> None:
    """Verify that missions track agent coordination events in logs."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # 1. Create mission with assigned agents metadata
    res = await mission_mgr.create_mission(goal="Multi-agent collaboration")
    mission_id = res["mission_id"]

    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
            res_db = await session.execute(stmt)
            mission = res_db.scalar_one()
            mission.assigned_agents = ["Planner", "Research Agent", "Browser Agent"]

    # 2. Start mission
    await mission_mgr.start_mission(mission_id)

    # Let it run a bit
    await asyncio.sleep(0.2)

    # 3. Retrieve database state and verify timeline contains agent logs
    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
        res_db = await session.execute(stmt)
        mission = res_db.scalar_one()
        assert "Research Agent" in mission.assigned_agents

        # Verify timeline events indicate step start/progress
        stmt_t = select(MissionTimelineModel).where(
            MissionTimelineModel.mission_id == mission_id,
            MissionTimelineModel.event_type == "TASK_STARTED",
        )
        res_t = await session.execute(stmt_t)
        timeline = res_t.scalars().all()
        assert len(timeline) > 0
        assert "Executing step" in timeline[0].description
