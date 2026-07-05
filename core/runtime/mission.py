"""
PHASE: 34
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/d42af1e8-69f8-4bf2-a03f-dc029da887c0/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import LifecycleInterface
from core.runtime.mission_models import (
    MissionCheckpointModel,
    MissionModel,
    MissionTimelineModel,
)

logger = logging.getLogger("jarvis.core.runtime.mission")


class MissionManager(LifecycleInterface):
    """Coordinates durable long-running missions and checkpoint states."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        event_bus: Any,
        vault_manager: Any,
        orchestrator: Any,
        planner: Any = None,
    ) -> None:
        """Initialize MissionManager with system dependencies."""
        self.settings = settings
        self.db_manager = db_manager
        self.event_bus = event_bus
        self.vault_manager = vault_manager
        self.orchestrator = orchestrator
        self.planner = planner
        self._active = False
        self._running_tasks: Dict[UUID, asyncio.Task[None]] = {}

    async def initialize(self) -> None:
        """Lifecycle initialization."""
        pass

    async def start(self) -> None:
        """Lifecycle start. Recovers any active running missions automatically."""
        self._active = True
        logger.info("MissionManager started.")
        await self._recover_active_missions()

    async def stop(self) -> None:
        """Lifecycle stop. Cancels active mission task loops gracefully."""
        self._active = False
        running_ids = list(self._running_tasks.keys())
        for m_id in running_ids:
            task = self._running_tasks.pop(m_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("MissionManager stopped.")

    async def shutdown(self) -> None:
        """Lifecycle shutdown."""
        await self.stop()
        logger.info("MissionManager shutdown complete.")

    async def create_mission(
        self, goal: str, budget_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create and persist a new mission in the CREATED state."""
        mission_id = uuid4()
        async with self.db_manager.session() as session:
            async with session.begin():
                mission = MissionModel(
                    mission_id=mission_id,
                    goal=goal,
                    status="CREATED",
                    budget_limit=budget_limit,
                    budget_used=0.0,
                    plan_data=None,
                    current_step=0,
                )
                session.add(mission)

        await self.append_timeline_event(mission_id, "CREATED", "Mission created.")
        return {
            "mission_id": mission_id,
            "status": "CREATED",
            "goal": goal,
            "budget_limit": budget_limit,
        }

    async def start_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Decompose goal and transition mission into running execution loops."""
        async with self.db_manager.session() as session:
            async with session.begin():
                stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()
                if not mission:
                    raise ValueError(f"Mission {mission_id} not found.")

                if mission.status != "CREATED":
                    raise ValueError(
                        f"Cannot start mission from state {mission.status}."
                    )

                mission.status = "PLANNING"
                await session.flush()

        await self.append_timeline_event(
            mission_id, "PLANNING", "Started goal planning and decomposition."
        )

        # Generate goal decomposition steps
        steps = await self._decompose_goal(mission.goal)

        async with self.db_manager.session() as session:
            async with session.begin():
                stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()
                mission.plan_data = steps
                mission.status = "RUNNING"
                await session.flush()

        await self.append_timeline_event(
            mission_id, "RUNNING", f"Goal decomposed into {len(steps)} steps. Running."
        )

        # Spawn background execution task loop
        if self._active:
            task = asyncio.create_task(self._execute_mission_loop(mission_id))
            self._running_tasks[mission_id] = task

        return {"mission_id": mission_id, "status": "RUNNING", "steps": steps}

    async def pause_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Suspend the active step loop of a running mission."""
        async with self.db_manager.session() as session:
            async with session.begin():
                stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()
                if not mission:
                    raise ValueError(f"Mission {mission_id} not found.")

                if mission.status not in ("RUNNING", "PLANNING", "WAITING_APPROVAL"):
                    raise ValueError(f"Cannot pause mission in state {mission.status}.")

                mission.status = "PAUSED"
                await session.flush()

        # Stop loop task
        if mission_id in self._running_tasks:
            task = self._running_tasks.pop(mission_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self.append_timeline_event(mission_id, "PAUSED", "Mission paused.")
        return {"mission_id": mission_id, "status": "PAUSED"}

    async def resume_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Reload latest checkpoint and resume execution loop."""
        async with self.db_manager.session() as session:
            async with session.begin():
                stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()
                if not mission:
                    raise ValueError(f"Mission {mission_id} not found.")

                if mission.status not in ("PAUSED", "WAITING_APPROVAL"):
                    raise ValueError(
                        f"Cannot resume mission in state {mission.status}."
                    )

                mission.status = "RUNNING"
                await session.flush()

        await self.append_timeline_event(
            mission_id,
            "RUNNING",
            f"Resuming execution from step index {mission.current_step}.",
        )

        # Spawn execution loop task
        if self._active:
            task = asyncio.create_task(self._execute_mission_loop(mission_id))
            self._running_tasks[mission_id] = task

        return {"mission_id": mission_id, "status": "RUNNING"}

    async def cancel_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Abort execution and mark mission as CANCELLED."""
        async with self.db_manager.session() as session:
            async with session.begin():
                stmt = select(MissionModel).where(MissionModel.mission_id == mission_id)
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()
                if not mission:
                    raise ValueError(f"Mission {mission_id} not found.")

                mission.status = "CANCELLED"
                await session.flush()

        # Stop loop task
        if mission_id in self._running_tasks:
            task = self._running_tasks.pop(mission_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self.append_timeline_event(mission_id, "CANCELLED", "Mission cancelled.")
        return {"mission_id": mission_id, "status": "CANCELLED"}

    async def create_checkpoint(
        self, mission_id: UUID, step_index: int, state_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Append an immutable state checkpoint to the database."""
        checkpoint_id = uuid4()
        async with self.db_manager.session() as session:
            async with session.begin():
                checkpoint = MissionCheckpointModel(
                    checkpoint_id=checkpoint_id,
                    mission_id=mission_id,
                    step_index=step_index,
                    state_data=state_data,
                )
                session.add(checkpoint)

        return {"checkpoint_id": checkpoint_id, "step_index": step_index}

    async def rollback_to_checkpoint(
        self, mission_id: UUID, checkpoint_id: UUID
    ) -> Dict[str, Any]:
        """Roll back the mission to a previous checkpoint index."""
        async with self.db_manager.session() as session:
            async with session.begin():
                # Fetch checkpoint
                stmt = select(MissionCheckpointModel).where(
                    MissionCheckpointModel.checkpoint_id == checkpoint_id
                )
                res = await session.execute(stmt)
                checkpoint = res.scalar_one_or_none()
                if not checkpoint:
                    raise ValueError(f"Checkpoint {checkpoint_id} not found.")

                # Fetch mission
                stmt_m = select(MissionModel).where(
                    MissionModel.mission_id == mission_id
                )
                res_m = await session.execute(stmt_m)
                mission = res_m.scalar_one_or_none()
                if not mission:
                    raise ValueError(f"Mission {mission_id} not found.")

                # Roll back step
                mission.current_step = checkpoint.step_index
                mission.status = "PAUSED"
                await session.flush()

        # Cancel any active running task
        if mission_id in self._running_tasks:
            task = self._running_tasks.pop(mission_id)
            task.cancel()

        await self.append_timeline_event(
            mission_id,
            "PAUSED",
            f"Rolled back to checkpoint {checkpoint_id} (step index {checkpoint.step_index}).",
        )
        return {"mission_id": mission_id, "status": "PAUSED", "current_step": checkpoint.step_index}

    async def append_timeline_event(
        self, mission_id: UUID, event_type: str, description: str
    ) -> None:
        """Write an append-only timeline event log."""
        event_id = uuid4()
        async with self.db_manager.session() as session:
            async with session.begin():
                event = MissionTimelineModel(
                    event_id=event_id,
                    mission_id=mission_id,
                    event_type=event_type,
                    description=description,
                )
                session.add(event)

    async def _decompose_goal(self, goal: str) -> List[Dict[str, Any]]:
        """Decompose a mission goal into discrete execution steps."""
        # Standard default decomposition. Real systems would invoke a Planner model.
        return [
            {
                "step": 0,
                "description": f"Gather research data for: {goal}",
                "estimated_cost": 2.50,
                "required_permissions": ["file_read"],
            },
            {
                "step": 1,
                "description": "Execute script tests validation",
                "estimated_cost": 5.00,
                "required_permissions": ["cli"],
            },
            {
                "step": 2,
                "description": f"Write summary report for: {goal}",
                "estimated_cost": 1.50,
                "required_permissions": ["file_write"],
            },
        ]

    async def _recover_active_missions(self) -> None:
        """Query running missions and restart their execution task loops."""
        async with self.db_manager.session() as session:
            stmt = select(MissionModel).where(MissionModel.status == "RUNNING")
            res = await session.execute(stmt)
            active_missions = res.scalars().all()
            for m in active_missions:
                task = asyncio.create_task(self._execute_mission_loop(m.mission_id))
                self._running_tasks[m.mission_id] = task
                logger.info("Recovered active mission %s on boot.", m.mission_id)

    async def _execute_mission_loop(self, mission_id: UUID) -> None:
        """Background loop executing mission steps sequentially."""
        try:
            while self._active:
                # 1. Fetch current state of mission
                async with self.db_manager.session() as session:
                    stmt = select(MissionModel).where(
                        MissionModel.mission_id == mission_id
                    )
                    res = await session.execute(stmt)
                    mission = res.scalar_one_or_none()

                if not mission or mission.status != "RUNNING":
                    break

                plan = mission.plan_data or []
                curr_step = mission.current_step

                # Check if mission has completed all steps
                if curr_step >= len(plan):
                    async with self.db_manager.session() as session:
                        async with session.begin():
                            stmt = select(MissionModel).where(
                                MissionModel.mission_id == mission_id
                            )
                            res = await session.execute(stmt)
                            m = res.scalar_one()
                            m.status = "COMPLETED"
                    await self.append_timeline_event(
                        mission_id, "COMPLETED", "All steps executed successfully."
                    )
                    break

                step = plan[curr_step]
                step_desc = step.get("description", "")
                step_cost = step.get("estimated_cost", 0.0)

                # 2. Check Approval Gates & Budget limits
                # Pauses automatically on elevated budget limits, destructive keywords, or custom tier rules
                budget_exceeded = (
                    mission.budget_limit is not None
                    and (mission.budget_used + step_cost) > mission.budget_limit
                )
                destructive_action = any(
                    w in step_desc.lower()
                    for w in (
                        "delete",
                        "remove",
                        "destroy",
                        "wipe",
                        "format",
                        "sudo",
                        "drop",
                        "truncate",
                    )
                )

                if budget_exceeded or destructive_action:
                    async with self.db_manager.session() as session:
                        async with session.begin():
                            stmt = select(MissionModel).where(
                                MissionModel.mission_id == mission_id
                            )
                            res = await session.execute(stmt)
                            m = res.scalar_one()
                            m.status = "WAITING_APPROVAL"

                    reason = "Budget limit exceeded" if budget_exceeded else "High-risk action detected"
                    await self.append_timeline_event(
                        mission_id,
                        "WAITING_APPROVAL",
                        f"Paused at step {curr_step}: Awaiting human approval ({reason}).",
                    )
                    break

                # 3. Execute step (Reuse existing Swarm Orchestrator coordinator)
                await self.append_timeline_event(
                    mission_id,
                    "TASK_STARTED",
                    f"Executing step {curr_step}: {step_desc}",
                )

                # Simulated task execution on Swarm Orchestrator placeholder
                # if self.orchestrator:
                #     await self.orchestrator.spawn_task(...)
                pass

                # Simulate execution duration
                await asyncio.sleep(0.1)

                # 4. Commit Step Execution Progress & Save Checkpoint
                async with self.db_manager.session() as session:
                    async with session.begin():
                        stmt = select(MissionModel).where(
                            MissionModel.mission_id == mission_id
                        )
                        res = await session.execute(stmt)
                        m = res.scalar_one()
                        m.current_step = curr_step + 1
                        m.budget_used += step_cost

                # Save Checkpoint
                await self.create_checkpoint(
                    mission_id,
                    curr_step + 1,
                    state_data={"step": curr_step, "status": "SUCCESS"},
                )

                # Save timeline event
                await self.append_timeline_event(
                    mission_id, "TASK_FINISHED", f"Finished step {curr_step}."
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Error in mission execution loop: %s", e)
            async with self.db_manager.session() as session:
                async with session.begin():
                    stmt = select(MissionModel).where(
                        MissionModel.mission_id == mission_id
                    )
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        m.status = "FAILED"
            await self.append_timeline_event(
                mission_id, "FAILED", f"Execution failed due to exception: {e}"
            )
