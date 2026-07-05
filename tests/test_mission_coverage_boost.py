"""JARVIS OS - Mission Manager Extra Coverage Tests."""

import asyncio
from typing import Any, Dict
from uuid import uuid4

import pytest
from sqlalchemy import select

from core.exceptions import JarvisMemoryError
from core.runtime.mission_models import MissionModel


@pytest.mark.asyncio
async def test_mission_manager_error_paths(setup_mission_env: Dict[str, Any]) -> None:
    """Verify ValueError branches for non-existent missions or invalid transitions."""
    mission_mgr = setup_mission_env["mission_mgr"]
    non_existent_id = uuid4()

    # 1. Non-existent missions (wrapped in JarvisMemoryError by session manager)
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.start_mission(non_existent_id)
    assert "not found" in str(exc_info.value)

    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.pause_mission(non_existent_id)
    assert "not found" in str(exc_info.value)

    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.resume_mission(non_existent_id)
    assert "not found" in str(exc_info.value)

    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.cancel_mission(non_existent_id)
    assert "not found" in str(exc_info.value)

    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.rollback_to_checkpoint(non_existent_id, uuid4())
    assert "not found" in str(exc_info.value)

    # Checkpoint not found
    res = await mission_mgr.create_mission("Dummy Goal")
    m_id = res["mission_id"]
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.rollback_to_checkpoint(m_id, uuid4())
    assert "Checkpoint" in str(exc_info.value)

    # 2. State transition violations
    # Resume from CREATED
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.resume_mission(m_id)
    assert "Cannot resume" in str(exc_info.value)

    # Pause from CREATED
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.pause_mission(m_id)
    assert "Cannot pause" in str(exc_info.value)

    # Start planning -> running
    await mission_mgr.start_mission(m_id)

    # Double start from RUNNING
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.start_mission(m_id)
    assert "Cannot start" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mission_completion_and_failure(
    setup_mission_env: Dict[str, Any],
) -> None:
    """Verify mission completion detection and crash/failure tracking in execution loop."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # 1. COMPLETED state (when current_step >= len(plan))
    res = await mission_mgr.create_mission("Completion check")
    m_id = res["mission_id"]
    await mission_mgr.start_mission(m_id)
    await mission_mgr.pause_mission(m_id)  # Pause to avoid background loop race

    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == m_id)
            res_db = await session.execute(stmt)
            m = res_db.scalar_one()
            m.current_step = 3  # Force it to the end
            m.status = "PAUSED"  # Ensure it is marked paused

    await mission_mgr.resume_mission(m_id)  # Resuming runs the loop again
    await asyncio.sleep(0.2)

    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == m_id)
        res_db = await session.execute(stmt)
        m = res_db.scalar_one()
        assert m.status == "COMPLETED"

    # 2. FAILED state (exception in loop)
    res_fail = await mission_mgr.create_mission("Failure check")
    fail_id = res_fail["mission_id"]

    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == fail_id)
            res_db = await session.execute(stmt)
            m = res_db.scalar_one()
            m.plan_data = ["invalid string step to cause AttributeError"]
            m.status = "RUNNING"

    # Start loop manually
    task = asyncio.create_task(mission_mgr._execute_mission_loop(fail_id))
    mission_mgr._running_tasks[fail_id] = task

    await asyncio.sleep(0.1)

    async with db_manager.session() as session:
        stmt = select(MissionModel).where(MissionModel.mission_id == fail_id)
        res_db = await session.execute(stmt)
        m = res_db.scalar_one()
        assert m.status == "FAILED"


@pytest.mark.asyncio
async def test_rollback_missing_mission(setup_mission_env: Dict[str, Any]) -> None:
    """Verify rollback raises an error if the checkpoint exists but the mission is missing from DB."""
    from sqlalchemy import delete

    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    # Create mission and checkpoint
    res = await mission_mgr.create_mission("Rollback orphan check")
    m_id = res["mission_id"]
    cp = await mission_mgr.create_checkpoint(m_id, 1, {"data": "test"})

    # Delete the mission row directly
    async with db_manager.session() as session:
        async with session.begin():
            await session.execute(
                delete(MissionModel).where(MissionModel.mission_id == m_id)
            )

    # Calling rollback should now raise mission not found
    with pytest.raises(JarvisMemoryError) as exc_info:
        await mission_mgr.rollback_to_checkpoint(m_id, cp["checkpoint_id"])
    assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mission_loop_status_break(setup_mission_env: Dict[str, Any]) -> None:
    """Verify that execution loop exits if the mission status is modified to not RUNNING."""
    mission_mgr = setup_mission_env["mission_mgr"]
    db_manager = setup_mission_env["db_manager"]

    res = await mission_mgr.create_mission("Loop break check")
    m_id = res["mission_id"]
    await mission_mgr.start_mission(m_id)

    # Modify status to CREATED directly in DB (bypassing normal pause which cancels the task)
    async with db_manager.session() as session:
        async with session.begin():
            stmt = select(MissionModel).where(MissionModel.mission_id == m_id)
            res_db = await session.execute(stmt)
            m = res_db.scalar_one()
            m.status = "CREATED"

    # Allow loop task to run its next iteration, see status != RUNNING, and exit
    await asyncio.sleep(0.2)

    # The task's loop has exited, so the task should be marked as done
    task = mission_mgr._running_tasks[m_id]
    assert task.done()
