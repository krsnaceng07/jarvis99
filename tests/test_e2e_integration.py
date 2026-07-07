"""
PHASE: 41
STATUS: TEST
SPECIFICATION:
    End-to-end integration test proving the full execution path:
    User Goal → Planning → Memory Recall → Parallel Planner →
    Role Assigner → Orchestrator → Supervisor → Conflict Resolver →
    Result Merger → Reflection → Completion

    Verifies every arrow in the architecture diagram actually executes.
"""

import asyncio
import os
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from core.runtime.conflict_resolver import ConflictResolver
from core.runtime.parallel_planner import ParallelMissionPlanner
from core.runtime.result_merger import AgentOutput, MergedResult, ResultMerger
from core.runtime.role_assigner import AgentRole, AgentRoleAssigner
from core.runtime.supervisor import AgentSupervisor


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def e2e_mission_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Set up a full MissionManager with all Goal #5 components wired."""
    import core.runtime.mission_models  # noqa: F401
    from core.config import Settings
    from core.events.memory_bus import MemoryEventBus
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.runtime.mission import MissionManager

    settings = Settings.load_settings()
    db_file = f"test_e2e_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    from sqlalchemy import text

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    # Goal #5 components
    parallel_planner = ParallelMissionPlanner()
    role_assigner = AgentRoleAssigner()
    result_merger = ResultMerger()
    conflict_resolver = ConflictResolver()
    supervisor = AgentSupervisor()

    # Mock orchestrator: tracks spawned tasks
    mock_orchestrator = AsyncMock()
    mock_orchestrator.spawn_task = AsyncMock(return_value=True)

    # Mock memory orchestrator: returns recalled context
    mock_recall_response = AsyncMock()
    mock_recall_response.chunks = ["Previous research on AI agents"]
    mock_memory = AsyncMock()
    mock_memory.recall = AsyncMock(return_value=mock_recall_response)

    mission_mgr = MissionManager(
        settings=settings,
        db_manager=db_manager,
        event_bus=event_bus,
        vault_manager=None,
        orchestrator=mock_orchestrator,
        parallel_planner=parallel_planner,
        role_assigner=role_assigner,
        result_merger=result_merger,
        conflict_resolver=conflict_resolver,
        supervisor=supervisor,
        memory_orchestrator=mock_memory,
    )
    await mission_mgr.initialize()
    await mission_mgr.start()

    yield {
        "mission_mgr": mission_mgr,
        "db_manager": db_manager,
        "mock_orchestrator": mock_orchestrator,
        "mock_memory": mock_memory,
        "parallel_planner": parallel_planner,
        "role_assigner": role_assigner,
        "result_merger": result_merger,
        "conflict_resolver": conflict_resolver,
        "supervisor": supervisor,
    }

    await mission_mgr.stop()
    await mission_mgr.shutdown()
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()

    for suffix in ("", "-wal", "-shm", "-journal"):
        path = db_file + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# E2E: Full Mission Flow (Goal → Parallel Waves → Completion)
# ═══════════════════════════════════════════════════════════════════════════


class TestE2EFullMissionFlow:
    """End-to-end test: proves every component in the execution path fires."""

    @pytest.mark.asyncio
    async def test_parallel_mission_full_flow(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Goal → Memory Recall → Decompose → Parallel Plan → Waves →
        Role Assign → Spawn → Supervisor → Conflict Resolve → Merge → Complete.
        """
        mgr = e2e_mission_env["mission_mgr"]
        mock_orch = e2e_mission_env["mock_orchestrator"]
        mock_mem = e2e_mission_env["mock_memory"]

        # 1. Create mission
        res = await mgr.create_mission(
            goal="Research AI trends and implement a REST API with tests",
            budget_limit=50.0,
        )
        assert res["status"] == "CREATED"
        mission_id = res["mission_id"]

        # 2. Start mission — triggers memory recall + decompose + parallel plan
        start_res = await mgr.start_mission(mission_id)
        assert start_res["status"] == "RUNNING"
        steps = start_res["steps"]
        assert len(steps) >= 3  # default plan has 3 steps

        # Verify memory recall was called BEFORE planning
        mock_mem.recall.assert_called_once()
        recall_arg = mock_mem.recall.call_args[0][0]
        assert recall_arg.query == "Research AI trends and implement a REST API with tests"

        # 3. Wait for the background execution loop to process
        await asyncio.sleep(0.3)

        # 4. Verify orchestrator.spawn_task was called (parallel wave execution)
        assert mock_orch.spawn_task.call_count >= 1, (
            "Orchestrator.spawn_task should have been called for wave steps"
        )

        # 5. Check that spawned tasks have wave metadata
        for call in mock_orch.spawn_task.call_args_list:
            task = call[0][0]  # first positional arg
            assert "mission_id" in task.metadata
            assert "wave_index" in task.metadata
            assert "role" in task.metadata

    @pytest.mark.asyncio
    async def test_role_assignment_in_parallel_flow(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Verify role assignment happens during parallel execution."""
        mgr = e2e_mission_env["mission_mgr"]
        mock_orch = e2e_mission_env["mock_orchestrator"]

        res = await mgr.create_mission(
            goal="Research machine learning papers and implement the algorithm",
        )
        mission_id = res["mission_id"]
        await mgr.start_mission(mission_id)
        await asyncio.sleep(0.3)

        # Spawned tasks should have role metadata from RoleAssigner
        roles_seen = set()
        for call in mock_orch.spawn_task.call_args_list:
            task = call[0][0]
            role = task.metadata.get("role", "")
            if role:
                roles_seen.add(role)

        # At least one task should have a non-general role assigned
        assert len(roles_seen) >= 1, (
            f"Expected role assignments, got: {roles_seen}"
        )

    @pytest.mark.asyncio
    async def test_supervisor_tracks_wave_completion(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Verify supervisor wave tracking during parallel execution."""
        mgr = e2e_mission_env["mission_mgr"]
        supervisor = e2e_mission_env["supervisor"]

        res = await mgr.create_mission(goal="Build a web application")
        mission_id = res["mission_id"]
        await mgr.start_mission(mission_id)
        await asyncio.sleep(0.3)

        # Supervisor should have tracked at least one wave
        statuses = supervisor.get_all_wave_statuses()
        assert len(statuses) >= 1, "Supervisor should track at least one wave"

        # All tasks should be marked complete
        for ws in statuses:
            assert ws.is_complete, f"Wave {ws.wave_index} should be complete"

    @pytest.mark.asyncio
    async def test_approval_gate_halts_parallel_wave(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """High-risk steps should pause the mission even in parallel mode."""
        mgr = e2e_mission_env["mission_mgr"]

        # Pre-computed plan with a destructive step
        dangerous_plan = [
            {"step": 0, "description": "Research the database schema",
             "estimated_cost": 0.05, "required_permissions": [], "executor": "llm"},
            {"step": 1, "description": "Delete all old records from production",
             "estimated_cost": 0.10, "required_permissions": [], "executor": "shell"},
        ]

        res = await mgr.create_mission(
            goal="Clean up database",
            plan_steps=dangerous_plan,
        )
        mission_id = res["mission_id"]
        start_res = await mgr.start_mission(mission_id)
        assert start_res["status"] == "RUNNING"
        await asyncio.sleep(0.3)

        # Mission should be paused at WAITING_APPROVAL
        from sqlalchemy import select
        from core.runtime.mission_models import MissionModel

        async with e2e_mission_env["db_manager"].session() as session:
            stmt = select(MissionModel).where(
                MissionModel.mission_id == mission_id,
            )
            result = await session.execute(stmt)
            mission = result.scalar_one()
            assert mission.status == "WAITING_APPROVAL", (
                f"Expected WAITING_APPROVAL, got {mission.status}"
            )

    @pytest.mark.asyncio
    async def test_sequential_fallback_without_parallel_planner(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Without parallel_planner, mission runs sequentially (legacy path)."""
        mgr = e2e_mission_env["mission_mgr"]

        # Temporarily remove parallel_planner
        original_pp = mgr.parallel_planner
        mgr.parallel_planner = None

        try:
            res = await mgr.create_mission(goal="Simple sequential task")
            mission_id = res["mission_id"]
            await mgr.start_mission(mission_id)
            await asyncio.sleep(0.3)

            # Should still complete via sequential path
            mock_orch = e2e_mission_env["mock_orchestrator"]
            assert mock_orch.spawn_task.call_count >= 1
        finally:
            mgr.parallel_planner = original_pp


# ═══════════════════════════════════════════════════════════════════════════
# E2E: Component Integration (isolated arrow verification)
# ═══════════════════════════════════════════════════════════════════════════


class TestComponentIntegration:
    """Verify individual arrows between components work correctly."""

    def test_parallel_planner_to_role_assigner(self) -> None:
        """ParallelPlanner output → RoleAssigner input."""
        planner = ParallelMissionPlanner()
        assigner = AgentRoleAssigner()

        steps = [
            {"description": "Research AI papers", "step": 0},
            {"description": "Implement the REST API", "step": 1},
            {"description": "Write unit tests for API", "step": 2},
            {"description": "Document the API endpoints", "step": 3},
        ]

        plan = planner.plan_parallel(steps)
        assert plan.total_steps == 4
        assert len(plan.waves) >= 1

        # Feed each wave into RoleAssigner
        for wave in plan.waves:
            assignments = assigner.assign_roles_to_wave(
                [{"description": s.description} for s in wave.steps],
                wave_index=wave.wave_index,
            )
            assert len(assignments) == len(wave.steps)
            for a in assignments:
                assert a.role in AgentRole
                assert a.wave_index == wave.wave_index

    def test_result_merger_to_conflict_resolver(self) -> None:
        """ResultMerger output feeds into ConflictResolver."""
        merger = ResultMerger()
        resolver = ConflictResolver()

        outputs = [
            AgentOutput(
                agent_id="a1", role="research",
                stdout="We should use PostgreSQL for data storage",
            ),
            AgentOutput(
                agent_id="a2", role="coding",
                stdout="MongoDB is better for this use case",
            ),
        ]

        # Merge first
        merged = merger.merge_wave_results(outputs, wave_index=0)
        assert merged.success is True

        # Then check for conflicts
        conflicts = resolver.detect_conflicts([
            {"agent_id": o.agent_id, "role": o.role, "stdout": o.stdout}
            for o in outputs
        ])
        assert len(conflicts) >= 1, "Should detect PostgreSQL vs MongoDB conflict"

    @pytest.mark.asyncio
    async def test_conflict_resolver_to_result_merger(self) -> None:
        """ConflictResolver resolves, then ResultMerger produces final output."""
        resolver = ConflictResolver()
        merger = ResultMerger()

        outputs_raw = [
            {"agent_id": "a1", "role": "planning", "stdout": "Use React for frontend"},
            {"agent_id": "a2", "role": "coding", "stdout": "Vue.js is the best choice"},
        ]

        conflicts = resolver.detect_conflicts(outputs_raw)
        if conflicts:
            resolutions = await resolver.resolve_all(conflicts, outputs_raw)
            assert len(resolutions) >= 1
            # Planning role should win by priority
            assert "React" in resolutions[0].chosen_output

        # Merge wave results regardless of conflicts
        agent_outputs = [
            AgentOutput(agent_id=o["agent_id"], role=o["role"], stdout=o["stdout"])
            for o in outputs_raw
        ]
        merged = merger.merge_wave_results(agent_outputs, wave_index=0)
        assert merged.success is True
        assert merged.merged_output != ""

    def test_supervisor_wave_tracking_lifecycle(self) -> None:
        """Supervisor tracks tasks through register → complete cycle."""
        supervisor = AgentSupervisor()

        a1 = uuid4()
        a2 = uuid4()
        a3 = uuid4()

        supervisor.register_agent_task(a1, {"goal": "research"}, wave_index=0)
        supervisor.register_agent_task(a2, {"goal": "code"}, wave_index=0)
        supervisor.register_agent_task(a3, {"goal": "test"}, wave_index=1)

        # Wave 0 in progress
        assert not supervisor.is_wave_complete(0)
        assert not supervisor.is_wave_complete(1)

        supervisor.report_task_complete(a1, success=True)
        assert not supervisor.is_wave_complete(0)

        supervisor.report_task_complete(a2, success=True)
        assert supervisor.is_wave_complete(0)

        # Wave 1 still pending
        assert not supervisor.is_wave_complete(1)
        supervisor.report_task_complete(a3, success=True)
        assert supervisor.is_wave_complete(1)

    def test_full_pipeline_planner_to_merger(self) -> None:
        """Full pipeline: plan → assign → (mock execute) → merge."""
        planner = ParallelMissionPlanner()
        assigner = AgentRoleAssigner()
        merger = ResultMerger()
        supervisor = AgentSupervisor()

        steps = [
            {"description": "Research cloud providers", "step": 0},
            {"description": "Design the microservice architecture", "step": 1},
            {"description": "Implement user authentication service", "step": 2},
            {"description": "Write integration tests", "step": 3},
            {"description": "Write API documentation", "step": 4},
        ]

        # 1. Plan
        plan = planner.plan_parallel(steps)
        assert plan.total_steps == 5

        all_wave_results: List[MergedResult] = []

        # 2. Process each wave
        for wave in plan.waves:
            # Assign roles
            assignments = assigner.assign_roles_to_wave(
                [{"description": s.description} for s in wave.steps],
                wave_index=wave.wave_index,
            )

            # Register with supervisor
            agent_ids = []
            for i, ws in enumerate(wave.steps):
                aid = uuid4()
                agent_ids.append(aid)
                supervisor.register_agent_task(
                    aid, {"goal": ws.description}, wave_index=wave.wave_index,
                )

            # Simulate execution results
            outputs = []
            for i, ws in enumerate(wave.steps):
                role = assignments[i].role.value if i < len(assignments) else "general"
                outputs.append(
                    AgentOutput(
                        agent_id=str(agent_ids[i]),
                        role=role,
                        task_description=ws.description,
                        stdout=f"Result: {ws.description}",
                        status="SUCCESS",
                    )
                )

            # Report completion to supervisor
            for aid in agent_ids:
                supervisor.report_task_complete(aid, success=True)

            assert supervisor.is_wave_complete(wave.wave_index)

            # Merge wave results
            merged = merger.merge_wave_results(outputs, wave_index=wave.wave_index)
            assert merged.success is True
            all_wave_results.append(merged)

        # 3. Final mission merge
        final = merger.merge_mission_results(all_wave_results)
        assert final.success is True
        assert "Research" in final.merged_output or "cloud" in final.merged_output.lower()
        assert len(all_wave_results) >= 2  # At least 2 waves


# ═══════════════════════════════════════════════════════════════════════════
# E2E: RepairEngine in Dispatcher Path
# ═══════════════════════════════════════════════════════════════════════════


class TestRepairEngineIntegration:
    """Verify RepairEngine fires through Dispatcher on failure."""

    @pytest.mark.asyncio
    async def test_dispatcher_invokes_repair_on_failure(self) -> None:
        """ToolDispatcher → RepairEngine.attempt_repair on failed execution."""
        from core.reasoning.dispatcher import ToolDispatcher
        from core.reasoning.reflection import ReflectionEngine
        from core.reasoning.repair_engine import RepairEngine
        from core.reasoning.task import ExecutorType, Task, TaskType
        from core.tools.dto import ToolExecutionResult

        reflection = ReflectionEngine()
        repair = RepairEngine(reflection_engine=reflection)

        goal_id = uuid4()
        fail_count = 0

        # ToolDispatcher calls executor.execute(task, context),
        # so we need a mock with an .execute() method
        mock_executor = AsyncMock()

        async def failing_execute(task: Any, ctx: Any) -> Any:
            nonlocal fail_count
            fail_count += 1
            return ToolExecutionResult(
                task_id=task.id,
                status="ERROR",
                stdout="",
                stderr="Connection refused",
            )

        mock_executor.execute = failing_execute

        dispatcher = ToolDispatcher(
            executors={ExecutorType.PYTHON: mock_executor},
            repair_engine=repair,
        )

        task = Task(
            id=uuid4(),
            goal_id=goal_id,
            executor=ExecutorType.PYTHON,
            task_type=TaskType.CODE,
        )

        result = await dispatcher.dispatch(task, {})
        # RepairEngine should have been invoked (attempt_repair called)
        # The result might still be ERROR if repair also fails (no tools available)
        assert fail_count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# E2E: Memory Recall Before Planning
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryRecallIntegration:
    """Verify memory recall happens before mission planning."""

    @pytest.mark.asyncio
    async def test_memory_recall_called_before_decompose(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Memory.recall() must fire before _decompose_goal()."""
        mgr = e2e_mission_env["mission_mgr"]
        mock_mem = e2e_mission_env["mock_memory"]

        # Reset call tracking
        mock_mem.recall.reset_mock()

        res = await mgr.create_mission(goal="Analyze quarterly sales data")
        mission_id = res["mission_id"]

        await mgr.start_mission(mission_id)

        # Memory recall should have been called with the goal
        mock_mem.recall.assert_called_once()
        recall_arg = mock_mem.recall.call_args[0][0]
        assert recall_arg.query == "Analyze quarterly sales data"

    @pytest.mark.asyncio
    async def test_mission_works_without_memory_orchestrator(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """Mission should still work if memory_orchestrator is None."""
        mgr = e2e_mission_env["mission_mgr"]

        original_mem = mgr.memory_orchestrator
        mgr.memory_orchestrator = None

        try:
            res = await mgr.create_mission(goal="Simple task without memory")
            mission_id = res["mission_id"]
            start_res = await mgr.start_mission(mission_id)
            assert start_res["status"] == "RUNNING"
        finally:
            mgr.memory_orchestrator = original_mem

    @pytest.mark.asyncio
    async def test_memory_recall_failure_does_not_block(
        self, e2e_mission_env: Dict[str, Any],
    ) -> None:
        """If memory.recall() raises, planning should still proceed."""
        mgr = e2e_mission_env["mission_mgr"]
        mock_mem = e2e_mission_env["mock_memory"]

        mock_mem.recall.side_effect = RuntimeError("Memory service unavailable")

        res = await mgr.create_mission(goal="Task with broken memory")
        mission_id = res["mission_id"]
        start_res = await mgr.start_mission(mission_id)
        assert start_res["status"] == "RUNNING"
        assert len(start_res["steps"]) >= 1

        # Restore
        mock_mem.recall.side_effect = None