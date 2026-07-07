"""
PHASE: 41
STATUS: TEST
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Tests for: AgentRoleAssigner, ParallelMissionPlanner, ResultMerger,
           ConflictResolver, AgentSupervisor, DeadlockDetector.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.runtime.role_assigner import AgentRole, AgentRoleAssigner
from core.runtime.parallel_planner import ParallelMissionPlanner
from core.runtime.result_merger import AgentOutput, MergedResult, ResultMerger
from core.runtime.conflict_resolver import Conflict, ConflictResolver
from core.runtime.supervisor import AgentSupervisor
from core.runtime.deadlock_detector import DeadlockDetector


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.1: AgentRoleAssigner
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentRoleAssigner:
    def test_classify_research_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Research the latest AI papers") == AgentRole.RESEARCH

    def test_classify_coding_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Implement the REST API endpoint") == AgentRole.CODING

    def test_classify_testing_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Write unit tests for the auth module") == AgentRole.TESTING

    def test_classify_documentation_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Write README documentation") == AgentRole.DOCUMENTATION

    def test_classify_planning_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Design the system architecture") == AgentRole.PLANNING

    def test_classify_review_task(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Review the pull request code") == AgentRole.REVIEW

    def test_classify_ambiguous_defaults_to_general(self) -> None:
        assigner = AgentRoleAssigner()
        assert assigner.classify_role("Do the thing") == AgentRole.GENERAL

    def test_get_role_capabilities(self) -> None:
        assigner = AgentRoleAssigner()
        caps = assigner.get_role_capabilities(AgentRole.CODING)
        assert "python" in caps
        assert "file_write" in caps

    def test_assign_roles_to_wave(self) -> None:
        assigner = AgentRoleAssigner()
        steps = [
            {"description": "Research the topic"},
            {"description": "Implement the solution"},
        ]
        assignments = assigner.assign_roles_to_wave(steps, wave_index=0)
        assert len(assignments) == 2
        assert assignments[0].role == AgentRole.RESEARCH
        assert assignments[1].role == AgentRole.CODING
        assert all(a.wave_index == 0 for a in assignments)

    @pytest.mark.asyncio
    async def test_classify_role_llm_falls_back(self) -> None:
        assigner = AgentRoleAssigner()
        role = await assigner.classify_role_llm("Implement the API")
        assert role == AgentRole.CODING

    @pytest.mark.asyncio
    async def test_assign_agent_for_role_no_registry(self) -> None:
        assigner = AgentRoleAssigner()
        result = await assigner.assign_agent_for_role(AgentRole.CODING, "Build API")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.2: ParallelMissionPlanner
# ═══════════════════════════════════════════════════════════════════════════


class TestParallelMissionPlanner:
    def test_empty_steps(self) -> None:
        planner = ParallelMissionPlanner()
        plan = planner.plan_parallel([])
        assert plan.total_steps == 0
        assert len(plan.waves) == 0

    def test_single_step(self) -> None:
        planner = ParallelMissionPlanner()
        steps = [{"description": "Research the topic", "step": 0}]
        plan = planner.plan_parallel(steps)
        assert plan.total_steps == 1
        assert len(plan.waves) == 1

    def test_parallel_grouping(self) -> None:
        planner = ParallelMissionPlanner()
        steps = [
            {"description": "Research AI trends", "step": 0},
            {"description": "Design the architecture", "step": 1},
            {"description": "Implement the backend API", "step": 2},
            {"description": "Write unit tests", "step": 3},
            {"description": "Write documentation", "step": 4},
        ]
        plan = planner.plan_parallel(steps)

        assert plan.total_steps == 5
        assert len(plan.waves) >= 2

        first_wave_descs = [s.description for s in plan.waves[0].steps]
        has_research = any("Research" in d for d in first_wave_descs)
        assert has_research

    def test_same_phase_steps_grouped(self) -> None:
        planner = ParallelMissionPlanner()
        steps = [
            {"description": "Implement backend", "step": 0},
            {"description": "Build frontend", "step": 1},
            {"description": "Create API layer", "step": 2},
        ]
        plan = planner.plan_parallel(steps)
        assert len(plan.waves) >= 1
        total_steps_in_waves = sum(len(w.steps) for w in plan.waves)
        assert total_steps_in_waves == 3

    def test_flatten_plan(self) -> None:
        planner = ParallelMissionPlanner()
        steps = [
            {"description": "Research topic", "step": 0},
            {"description": "Implement solution", "step": 1},
        ]
        plan = planner.plan_parallel(steps)
        flat = planner.flatten_plan(plan)
        assert len(flat) == 2
        assert "wave_index" in flat[0]

    @pytest.mark.asyncio
    async def test_llm_plan_falls_back(self) -> None:
        planner = ParallelMissionPlanner()
        steps = [
            {"description": "Research", "step": 0},
            {"description": "Implement", "step": 1},
        ]
        plan = await planner.plan_parallel_llm(steps, "Build AI agent")
        assert plan.total_steps == 2


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.3: ResultMerger
# ═══════════════════════════════════════════════════════════════════════════


class TestResultMerger:
    def test_merge_empty(self) -> None:
        merger = ResultMerger()
        result = merger.merge_wave_results([])
        assert result.merged_output == ""
        assert result.conflicts_detected == 0

    def test_merge_single_output(self) -> None:
        merger = ResultMerger()
        outputs = [
            AgentOutput(agent_id="a1", role="research", stdout="Found 3 papers"),
        ]
        result = merger.merge_wave_results(outputs)
        assert "Found 3 papers" in result.merged_output
        assert result.success is True

    def test_merge_multiple_outputs(self) -> None:
        merger = ResultMerger()
        outputs = [
            AgentOutput(agent_id="a1", role="research", stdout="Research results"),
            AgentOutput(agent_id="a2", role="coding", stdout="Code completed"),
        ]
        result = merger.merge_wave_results(outputs, wave_index=1)
        assert "Research results" in result.merged_output
        assert "Code completed" in result.merged_output
        assert result.wave_index == 1

    def test_merge_with_failures(self) -> None:
        merger = ResultMerger()
        outputs = [
            AgentOutput(agent_id="a1", role="research", stdout="OK", status="SUCCESS"),
            AgentOutput(agent_id="a2", role="coding", status="ERROR", error="crash"),
        ]
        result = merger.merge_wave_results(outputs)
        assert result.success is False
        assert "1 agent(s) failed" in (result.error or "")

    def test_merge_all_failed(self) -> None:
        merger = ResultMerger()
        outputs = [
            AgentOutput(agent_id="a1", status="ERROR", error="fail1"),
            AgentOutput(agent_id="a2", status="ERROR", error="fail2"),
        ]
        result = merger.merge_wave_results(outputs)
        assert result.success is False

    def test_merge_mission_results(self) -> None:
        merger = ResultMerger()
        wave_results = [
            MergedResult(wave_index=0, merged_output="Research done", success=True),
            MergedResult(wave_index=1, merged_output="Code complete", success=True),
        ]
        final = merger.merge_mission_results(wave_results)
        assert "Research done" in final.merged_output
        assert "Code complete" in final.merged_output
        assert final.success is True


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.4: ConflictResolver
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictResolver:
    def test_detect_technology_conflict(self) -> None:
        resolver = ConflictResolver()
        outputs = [
            {"agent_id": "a1", "stdout": "We should use PostgreSQL for the database"},
            {"agent_id": "a2", "stdout": "MongoDB is the best choice for this project"},
        ]
        conflicts = resolver.detect_conflicts(outputs)
        assert len(conflicts) >= 1
        assert "postgresql" in conflicts[0].description.lower() or "mongodb" in conflicts[0].description.lower()

    def test_no_conflict_when_compatible(self) -> None:
        resolver = ConflictResolver()
        outputs = [
            {"agent_id": "a1", "stdout": "The API is ready"},
            {"agent_id": "a2", "stdout": "Tests are passing"},
        ]
        conflicts = resolver.detect_conflicts(outputs)
        assert len(conflicts) == 0

    def test_resolve_by_priority(self) -> None:
        resolver = ConflictResolver()
        conflict = Conflict(
            agent_a="a1", agent_b="a2",
            description="Tech conflict",
            output_a="Use PostgreSQL",
            output_b="Use MongoDB",
        )
        outputs = [
            {"agent_id": "a1", "role": "planning", "stdout": "Use PostgreSQL"},
            {"agent_id": "a2", "role": "coding", "stdout": "Use MongoDB"},
        ]
        resolution = resolver.resolve_by_priority(conflict, outputs)
        assert "Use PostgreSQL" in resolution.chosen_output
        assert resolution.strategy == "priority"

    @pytest.mark.asyncio
    async def test_resolve_llm_no_runtime(self) -> None:
        resolver = ConflictResolver()
        conflict = Conflict(
            agent_a="a1", agent_b="a2",
            description="Test conflict",
            output_a="Option A",
            output_b="Option B",
        )
        resolution = await resolver.resolve_llm(conflict)
        assert resolution.strategy == "default"
        assert resolution.confidence == 0.3

    @pytest.mark.asyncio
    async def test_resolve_all(self) -> None:
        resolver = ConflictResolver()
        conflicts = [
            Conflict(agent_a="a1", agent_b="a2", description="test"),
        ]
        outputs = [
            {"agent_id": "a1", "role": "planning", "stdout": "A"},
            {"agent_id": "a2", "role": "coding", "stdout": "B"},
        ]
        resolutions = await resolver.resolve_all(conflicts, outputs)
        assert len(resolutions) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.5: AgentSupervisor
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentSupervisor:
    def test_register_and_complete_task(self) -> None:
        supervisor = AgentSupervisor()
        agent_id = uuid4()
        supervisor.register_agent_task(agent_id, {"goal": "test"}, wave_index=0)

        wave = supervisor.get_wave_status(0)
        assert wave is not None
        assert wave.total_tasks == 1
        assert wave.in_progress == 1

        supervisor.report_task_complete(agent_id, success=True)
        wave = supervisor.get_wave_status(0)
        assert wave.completed == 1
        assert wave.is_complete is True

    def test_wave_complete_detection(self) -> None:
        supervisor = AgentSupervisor()
        a1 = uuid4()
        a2 = uuid4()
        supervisor.register_agent_task(a1, {"goal": "task1"}, wave_index=0)
        supervisor.register_agent_task(a2, {"goal": "task2"}, wave_index=0)

        assert not supervisor.is_wave_complete(0)

        supervisor.report_task_complete(a1, success=True)
        assert not supervisor.is_wave_complete(0)

        supervisor.report_task_complete(a2, success=True)
        assert supervisor.is_wave_complete(0)

    def test_failure_tracking(self) -> None:
        supervisor = AgentSupervisor()
        a1 = uuid4()
        a2 = uuid4()
        supervisor.register_agent_task(a1, {"goal": "t1"}, wave_index=0)
        supervisor.register_agent_task(a2, {"goal": "t2"}, wave_index=0)

        supervisor.report_task_complete(a1, success=False)
        supervisor.report_task_complete(a2, success=False)

        assert supervisor.should_abort_wave(0)

    def test_stalled_agent_detection(self) -> None:
        supervisor = AgentSupervisor()
        supervisor.AGENT_TIMEOUT_SECONDS = 0.0

        agent_id = uuid4()
        supervisor.register_agent_task(agent_id, {"goal": "test"}, wave_index=0)

        stalled = supervisor.get_stalled_agents()
        assert agent_id in stalled

    @pytest.mark.asyncio
    async def test_handle_stalled_agents(self) -> None:
        supervisor = AgentSupervisor()
        supervisor.AGENT_TIMEOUT_SECONDS = 0.0

        agent_id = uuid4()
        supervisor.register_agent_task(agent_id, {"goal": "test"}, wave_index=0)

        events = await supervisor.handle_stalled_agents()
        assert len(events) >= 1
        assert events[0].event_type == "timeout"

    @pytest.mark.asyncio
    async def test_handle_agent_failure(self) -> None:
        supervisor = AgentSupervisor()
        agent_id = uuid4()
        supervisor.register_agent_task(agent_id, {"goal": "test"}, wave_index=0)

        event = await supervisor.handle_agent_failure(agent_id, "OOM crash")
        assert event is not None
        assert event.event_type == "agent_failure"

    def test_get_all_wave_statuses(self) -> None:
        supervisor = AgentSupervisor()
        a1 = uuid4()
        a2 = uuid4()
        supervisor.register_agent_task(a1, {"goal": "t1"}, wave_index=0)
        supervisor.register_agent_task(a2, {"goal": "t2"}, wave_index=1)

        statuses = supervisor.get_all_wave_statuses()
        assert len(statuses) == 2
        assert statuses[0].wave_index == 0
        assert statuses[1].wave_index == 1


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5.6: DeadlockDetector
# ═══════════════════════════════════════════════════════════════════════════


class TestDeadlockDetector:
    def test_no_deadlock(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "C", "lock-2")

        cycles = detector.detect_cycles()
        assert len(cycles) == 0

    def test_simple_cycle_detected(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "C", "lock-2")
        detector.register_wait("C", "A", "lock-3")

        cycles = detector.detect_cycles()
        assert len(cycles) >= 1
        assert len(cycles[0].agents_involved) == 3

    def test_two_node_cycle(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "A", "lock-2")

        cycles = detector.detect_cycles()
        assert len(cycles) >= 1

    def test_victim_selection(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "A", "lock-2")

        cycles = detector.detect_cycles()
        assert cycles[0].victim != ""

    def test_clear_wait(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.clear_wait("A", "lock-1")
        assert len(detector.get_active_waits()) == 0

    def test_clear_agent(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("C", "A", "lock-2")
        detector.clear_agent("A")
        assert len(detector.get_active_waits()) == 0

    @pytest.mark.asyncio
    async def test_detect_and_resolve(self) -> None:
        mock_lock = MagicMock()
        mock_lock.release = AsyncMock(return_value=True)

        detector = DeadlockDetector(lock_manager=mock_lock)
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "A", "lock-2")

        deadlocks = await detector.detect_and_resolve()
        assert len(deadlocks) >= 1
        assert deadlocks[0].resolved is True

    def test_duplicate_wait_not_added(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("A", "B", "lock-1")
        assert len(detector.get_active_waits()) == 1

    def test_deadlock_history(self) -> None:
        detector = DeadlockDetector()
        detector.register_wait("A", "B", "lock-1")
        detector.register_wait("B", "A", "lock-2")
        detector.detect_cycles()
        assert len(detector.get_deadlock_history()) >= 1

    def test_build_wait_for_graph_from_locks(self) -> None:
        mock_lock = MagicMock()
        mock_lock._locks = {"lock-1": "B", "lock-2": "A"}

        detector = DeadlockDetector(lock_manager=mock_lock)
        detector.register_wait("A", "X", "lock-1")
        detector.build_wait_for_graph_from_locks()

        edges = detector.get_active_waits()
        assert edges[0].holder == "B"
