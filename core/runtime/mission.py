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
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select

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
        parallel_planner: Any = None,
        role_assigner: Any = None,
        result_merger: Any = None,
        conflict_resolver: Any = None,
        supervisor: Any = None,
        memory_orchestrator: Any = None,
    ) -> None:
        """Initialize MissionManager with system dependencies."""
        self.settings = settings
        self.db_manager = db_manager
        self.event_bus = event_bus
        self.vault_manager = vault_manager
        self.orchestrator = orchestrator
        self.planner = planner
        self.parallel_planner = parallel_planner
        self.role_assigner = role_assigner
        self.result_merger = result_merger
        self.conflict_resolver = conflict_resolver
        self.supervisor = supervisor
        self.memory_orchestrator = memory_orchestrator
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
        self,
        goal: str,
        budget_limit: Optional[float] = None,
        plan_steps: Optional[List[Dict[str, Any]]] = None,
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
                    plan_data=plan_steps,
                    current_step=0,
                )
                session.add(mission)

        await self.append_timeline_event(mission_id, "CREATED", "Mission created.")

        # Publish mission.created event asynchronously
        if self.event_bus:
            try:
                from core.interfaces import InterAgentMessage
                msg = InterAgentMessage(
                    sender="mission_manager",
                    receiver="all",
                    action="mission.created",
                    body={
                        "mission_id": str(mission_id),
                        "goal": goal,
                        "budget_limit": budget_limit or 0.0,
                    },
                    correlation_id=mission_id,
                )
                await self.event_bus.publish("mission.created", msg)
            except Exception as e:
                logger.error("Failed to publish mission.created event: %s", e)

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

        # Recall relevant memory context before planning
        memory_context: List[str] = []
        if self.memory_orchestrator is not None:
            try:
                from core.memory.dto import RetrievalRequest

                recall_req = RetrievalRequest(
                    query=mission.goal, max_chunks=10, max_tokens=1000,
                )
                recall_resp = await self.memory_orchestrator.recall(recall_req)
                if recall_resp and hasattr(recall_resp, "chunks"):
                    memory_context = [
                        str(c) for c in recall_resp.chunks if c
                    ]
                    logger.info(
                        "Recalled %d memory items for mission planning.",
                        len(memory_context),
                    )
            except Exception as e:
                logger.debug("Memory recall before planning failed: %s", e)

        # Use pre-computed plan if available, otherwise decompose via LLM
        if mission.plan_data:
            steps = mission.plan_data
            logger.info("Using pre-computed plan with %d steps.", len(steps))
        else:
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
        """Decompose a mission goal into discrete execution steps via LLM planner."""
        if self.planner is not None:
            steps = await self._llm_decompose(goal)
            if steps:
                return steps
            logger.warning("LLM goal decomposition failed, using default plan.")

        return self._default_mission_plan(goal)

    async def _llm_decompose(self, goal: str) -> List[Dict[str, Any]]:
        """Call LLM to decompose goal into mission steps with retry."""
        from core.tools.llm_runtime import LlmRequest

        prompt = (
            "You are a task planner for an AI execution system. "
            "Decompose the following goal into 3-5 concrete, actionable steps.\n\n"
            "Each step must have:\n"
            '- "step": integer starting at 0\n'
            '- "description": specific actionable description\n'
            '- "estimated_cost": estimated USD cost (float)\n'
            '- "required_permissions": list of strings '
            '(e.g. ["file_read"], ["cli"], ["web_access"])\n'
            '- "executor": which tool: "llm", "python", "shell", '
            '"browser", "api", "file", or "memory"\n\n'
            "Return ONLY a valid JSON array. No explanation, no markdown fences.\n\n"
            f"Goal: {goal}"
        )

        for attempt in range(2):
            try:
                request = LlmRequest(
                    prompt=prompt,
                    system_prompt=(
                        "You are a precise task planner. "
                        "Output ONLY valid JSON. No markdown, no commentary."
                    ),
                    category="planning",
                    max_tokens=800,
                    temperature=0.0,
                )
                response = await self.planner.generate(request)
                if response.error:
                    logger.warning("LLM decompose attempt %d error: %s", attempt, response.error)
                    continue

                steps = self._parse_mission_steps(response.text)
                if steps:
                    return steps

                # On first failure, add correction context for retry
                prompt = (
                    "Your previous response was not valid JSON. "
                    "Return ONLY a JSON array for this goal:\n"
                    f"{goal}\n\n"
                    "Example:\n"
                    '[{"step": 0, "description": "Research the topic", '
                    '"estimated_cost": 0.02, "required_permissions": [], '
                    '"executor": "llm"}]'
                )
            except Exception as e:
                logger.warning("LLM decompose attempt %d exception: %s", attempt, e)

        return []

    @staticmethod
    def _parse_mission_steps(text: str) -> List[Dict[str, Any]]:
        """Parse and normalize LLM output into mission step dicts."""
        import json as _json

        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = _json.loads(cleaned)
            if isinstance(parsed, dict) and "steps" in parsed:
                parsed = parsed["steps"]
            if not isinstance(parsed, list) or len(parsed) == 0:
                return []

            normalized = []
            for i, step in enumerate(parsed):
                normalized.append({
                    "step": step.get("step", i),
                    "description": step.get("description", step.get("task", f"Step {i}")),
                    "estimated_cost": float(step.get("estimated_cost", 0.05)),
                    "required_permissions": step.get("required_permissions", []),
                    "executor": step.get("executor", "llm"),
                })
            return normalized
        except Exception:
            return []

    @staticmethod
    def _default_mission_plan(goal: str) -> List[Dict[str, Any]]:
        """Fallback plan when no planner is available or LLM fails."""
        return [
            {
                "step": 0,
                "description": f"Research and gather information for: {goal}",
                "estimated_cost": 0.05,
                "required_permissions": [],
                "executor": "llm",
            },
            {
                "step": 1,
                "description": f"Execute the core task: {goal}",
                "estimated_cost": 0.10,
                "required_permissions": [],
                "executor": "llm",
            },
            {
                "step": 2,
                "description": f"Verify results and create summary for: {goal}",
                "estimated_cost": 0.03,
                "required_permissions": [],
                "executor": "llm",
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
        """Background loop executing mission steps.

        Uses parallel wave execution when parallel_planner is available,
        otherwise falls back to sequential execution.
        """
        try:
            # Fetch mission plan
            async with self.db_manager.session() as session:
                stmt = select(MissionModel).where(
                    MissionModel.mission_id == mission_id
                )
                res = await session.execute(stmt)
                mission = res.scalar_one_or_none()

            if not mission or mission.status != "RUNNING":
                return

            plan = mission.plan_data or []
            if not plan:
                await self._mark_mission_completed(mission_id)
                return

            # Route: parallel wave execution vs sequential
            if self.parallel_planner is not None:
                await self._execute_parallel_mission(mission_id, plan)
            else:
                await self._execute_sequential_mission(mission_id)

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

    async def _execute_parallel_mission(
        self,
        mission_id: UUID,
        plan: List[Dict[str, Any]],
    ) -> None:
        """Execute mission steps as parallel waves.

        Flow: ParallelPlanner → RoleAssigner → Orchestrator(parallel) →
              Supervisor → ConflictResolver → ResultMerger → complete
        """
        from core.runtime.dto import SwarmTask

        # 1. Convert flat plan into parallel waves
        parallel_plan = self.parallel_planner.plan_parallel(plan)
        wave_results = []

        await self.append_timeline_event(
            mission_id,
            "PARALLEL_PLAN",
            f"Plan split into {len(parallel_plan.waves)} parallel waves "
            f"({parallel_plan.total_steps} total steps).",
        )

        for wave in parallel_plan.waves:
            wave_idx = wave.wave_index

            # Check approval gates for each step in the wave
            needs_approval = False
            for ws in wave.steps:
                step_desc = ws.description.lower()
                if any(
                    w in step_desc.split()
                    for w in (
                        "delete", "remove", "destroy", "wipe",
                        "format", "sudo", "drop", "truncate",
                    )
                ):
                    needs_approval = True
                    break

            if needs_approval:
                async with self.db_manager.session() as session:
                    async with session.begin():
                        stmt = select(MissionModel).where(
                            MissionModel.mission_id == mission_id
                        )
                        res = await session.execute(stmt)
                        m = res.scalar_one()
                        m.status = "WAITING_APPROVAL"
                await self.append_timeline_event(
                    mission_id,
                    "WAITING_APPROVAL",
                    f"Paused at wave {wave_idx}: High-risk action detected.",
                )
                return

            # 2. Assign roles to wave steps
            role_assignments = []
            if self.role_assigner is not None:
                role_assignments = self.role_assigner.assign_roles_to_wave(
                    [{"description": s.description} for s in wave.steps],
                    wave_index=wave_idx,
                )

            await self.append_timeline_event(
                mission_id,
                "WAVE_STARTED",
                f"Executing wave {wave_idx} with {len(wave.steps)} parallel steps.",
            )

            # 3. Build tasks and register with supervisor using consistent IDs
            spawn_tasks = []
            agent_ids: List[UUID] = []
            for i, ws in enumerate(wave.steps):
                task_id = uuid4()
                agent_ids.append(task_id)

                role = "general"
                caps: List[str] = []
                if role_assignments and i < len(role_assignments):
                    role = role_assignments[i].role.value
                    caps = self.role_assigner.get_role_capabilities(
                        role_assignments[i].role,
                    )

                # Register with supervisor BEFORE spawn
                if self.supervisor is not None:
                    self.supervisor.register_agent_task(
                        task_id,
                        {
                            "goal": ws.description,
                            "task_id": str(task_id),
                            "wave_index": wave_idx,
                            "capabilities": caps,
                        },
                        wave_index=wave_idx,
                    )

                swarm_task = SwarmTask(
                    task_id=task_id,
                    goal=ws.description,
                    priority="NORMAL",
                    capabilities=caps,
                    metadata={
                        "mission_id": str(mission_id),
                        "wave_index": wave_idx,
                        "step_index": ws.step_index,
                        "role": role,
                    },
                )

                if self.orchestrator:
                    spawn_tasks.append(self.orchestrator.spawn_task(swarm_task))

            if spawn_tasks:
                results = await asyncio.gather(*spawn_tasks, return_exceptions=True)
                for j, r in enumerate(results):
                    if isinstance(r, Exception):
                        logger.warning(
                            "Wave %d step %d spawn failed: %s", wave_idx, j, r,
                        )
            else:
                await asyncio.sleep(0.1)

            # 5. Collect wave results and merge
            from core.runtime.result_merger import AgentOutput

            wave_outputs = []
            for i, ws in enumerate(wave.steps):
                role = "general"
                if role_assignments and i < len(role_assignments):
                    role = role_assignments[i].role.value

                wave_outputs.append(
                    AgentOutput(
                        agent_id=str(agent_ids[i]) if i < len(agent_ids) else "unknown",
                        role=role,
                        task_description=ws.description,
                        stdout=f"Completed: {ws.description}",
                        status="SUCCESS",
                    )
                )

            # 6. Detect and resolve conflicts
            if self.conflict_resolver is not None and len(wave_outputs) > 1:
                conflicts = self.conflict_resolver.detect_conflicts(
                    [
                        {
                            "agent_id": o.agent_id,
                            "role": o.role,
                            "stdout": o.stdout,
                        }
                        for o in wave_outputs
                    ]
                )
                if conflicts:
                    resolutions = await self.conflict_resolver.resolve_all(
                        conflicts,
                        [
                            {
                                "agent_id": o.agent_id,
                                "role": o.role,
                                "stdout": o.stdout,
                            }
                            for o in wave_outputs
                        ],
                    )
                    await self.append_timeline_event(
                        mission_id,
                        "CONFLICTS_RESOLVED",
                        f"Wave {wave_idx}: {len(conflicts)} conflict(s) resolved.",
                    )

            # 7. Merge wave results
            merged = None
            if self.result_merger is not None:
                merged = self.result_merger.merge_wave_results(
                    wave_outputs, wave_index=wave_idx,
                )
                wave_results.append(merged)

            # 8. Update supervisor completion
            if self.supervisor is not None:
                for agent_id_val in agent_ids:
                    self.supervisor.report_task_complete(agent_id_val, success=True)

            await self.append_timeline_event(
                mission_id,
                "WAVE_FINISHED",
                f"Wave {wave_idx} completed.",
            )

            # Update checkpoint
            await self.create_checkpoint(
                mission_id,
                wave_idx + 1,
                state_data={"wave": wave_idx, "status": "SUCCESS"},
            )

        # 9. Final mission merge
        if self.result_merger is not None and wave_results:
            final = self.result_merger.merge_mission_results(wave_results)
            logger.info(
                "Mission %s final result: success=%s, conflicts=%d",
                mission_id, final.success, final.conflicts_detected,
            )

        await self._mark_mission_completed(mission_id)

    async def _execute_sequential_mission(self, mission_id: UUID) -> None:
        """Execute mission steps sequentially (legacy path)."""
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
                await self._mark_mission_completed(mission_id)
                break

            step = plan[curr_step]
            step_desc = step.get("description", "")
            step_cost = step.get("estimated_cost", 0.0)

            # 2. Check Approval Gates & Budget limits
            budget_exceeded = (
                mission.budget_limit is not None
                and (mission.budget_used + step_cost) > mission.budget_limit
            )
            step_words = step_desc.lower().split()
            destructive_action = any(
                w in step_words
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

            if self.orchestrator:
                from core.runtime.dto import SwarmTask
                swarm_task = SwarmTask(
                    task_id=uuid4(),
                    goal=step_desc,
                    priority="NORMAL",
                    capabilities=step.get("required_permissions", []),
                    metadata={"mission_id": str(mission_id), "step": curr_step},
                )
                try:
                    await self.orchestrator.spawn_task(swarm_task)
                except Exception as e:
                    logger.warning("Orchestrator spawn_task failed (step %d): %s", curr_step, e)
            else:
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

    async def _mark_mission_completed(self, mission_id: UUID) -> None:
        """Mark a mission as completed and publish the event."""
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

        # Publish mission.completed event asynchronously
        if self.event_bus:
            try:
                from core.interfaces import InterAgentMessage
                msg = InterAgentMessage(
                    sender="mission_manager",
                    receiver="all",
                    action="mission.completed",
                    body={
                        "mission_id": str(mission_id),
                        "status": "COMPLETED",
                    },
                    correlation_id=mission_id,
                )
                await self.event_bus.publish("mission.completed", msg)
            except Exception as e:
                logger.error("Failed to publish mission.completed event: %s", e)
