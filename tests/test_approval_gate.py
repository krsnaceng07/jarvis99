"""JARVIS OS - Mission Approval Gates and Safety Checks Tests."""

import asyncio
from typing import Any, Dict

import pytest
from sqlalchemy import select

from core.runtime.mission_models import MissionModel, MissionTimelineModel


@pytest.mark.asyncio
async def test_budget_gate(setup_mission_env: Dict[str, Any]) -> None:
    """Verify that a step exceeding the budget limit triggers a WAITING_APPROVAL status."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # 1. Create a mission with a budget limit lower than step costs (fallback steps: 0.05, 0.10, 0.03)
    res = await mission_mgr.create_mission(goal="Budget limit test", budget_limit=0.01)
    mission_id = res["mission_id"]

    # 2. Start the mission
    await mission_mgr.start_mission(mission_id)

    # Allow loop to process and pause
    await asyncio.sleep(0.2)

    # 3. Verify mission state was paused under WAITING_APPROVAL
    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
        res_db = await session.execute(stmt)
        mission = res_db.scalar_one()
        assert mission.status == "WAITING_APPROVAL"

        # Verify timeline log details
        stmt_t = select(MissionTimelineModel).where(
            MissionTimelineModel.mission_id == mission_id,
            MissionTimelineModel.event_type == "WAITING_APPROVAL",
        )
        res_t = await session.execute(stmt_t)
        timeline = res_t.scalars().all()
        assert len(timeline) > 0
        assert "Budget limit exceeded" in timeline[0].description


@pytest.mark.asyncio
async def test_destructive_safety_gate(setup_mission_env: Dict[str, Any]) -> None:
    """Verify that a step containing high-risk destructive keywords triggers safety pause."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # 1. Create mission
    res = await mission_mgr.create_mission(goal="Destructive delete safety test")
    mission_id = res["mission_id"]

    # 2. Update the steps to inject a destructive description
    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
            res_db = await session.execute(stmt)
            mission = res_db.scalar_one()
            mission.plan_data = [
                {
                    "step": 0,
                    "description": "rm -rf / --no-preserve-root delete all system files",
                    "estimated_cost": 0.0,
                }
            ]

    # 3. Start execution (which goes straight to the custom step)
    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
            res_db = await session.execute(stmt)
            mission = res_db.scalar_one()
            mission.status = "RUNNING"
            await session.flush()

    task = asyncio.create_task(mission_mgr._execute_mission_loop(mission_id))
    mission_mgr._running_tasks[mission_id] = task

    await asyncio.sleep(0.2)

    # 4. Verify mission state was paused under WAITING_APPROVAL
    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
        res_db = await session.execute(stmt)
        mission = res_db.scalar_one()
        assert mission.status == "WAITING_APPROVAL"

        # Verify timeline log details
        stmt_t = select(MissionTimelineModel).where(
            MissionTimelineModel.mission_id == mission_id,
            MissionTimelineModel.event_type == "WAITING_APPROVAL",
        )
        res_t = await session.execute(stmt_t)
        timeline = res_t.scalars().all()
        assert len(timeline) > 0
        assert "High-risk action detected" in timeline[0].description
