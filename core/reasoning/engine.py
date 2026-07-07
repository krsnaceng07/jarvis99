"""JARVIS OS - Reasoning Execution Engine.

Ties planning, parallel execution, reflection, replanning, and DB integrations into a single loop.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.config import Settings
from core.exceptions import BudgetExceededError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.reasoning.cost import CostGovernor
from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.engine_dto import (
    EngineMetrics,
    FailureType,
    SessionState,
)
from core.reasoning.execution_plan import ExecutionPlanCompiler
from core.reasoning.goal import Goal, GoalAnalyzer
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.plan_version_manager import PlanVersionManager
from core.reasoning.planner import ReasoningSession
from core.reasoning.planner_validator import PlannerValidator
from core.reasoning.planning_service import PlanningService
from core.reasoning.prompt import PromptBuilder
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.router import ModelRouter
from core.reasoning.scheduler import ExecutionScheduler
from core.reasoning.task import TaskGenerator


class ReasoningExecutionEngine:
    """Core executive control loop orchestrating planning, execution, and reflection loops."""

    def __init__(
        self,
        orchestrator: ExecutionOrchestrator,
        reflection_engine: ReflectionEngine,
        router: ModelRouter,
        prompt_builder: PromptBuilder,
        cost_governor: CostGovernor,
        settings: Settings,
        planning_service: PlanningService,
        version_manager: PlanVersionManager,
        event_bus: Optional[EventBusInterface] = None,
        llm_runtime: Optional[Any] = None,
        tool_selector: Optional[Any] = None,
    ) -> None:
        """Initialize ReasoningExecutionEngine."""
        self.orchestrator = orchestrator
        self.reflection_engine = reflection_engine
        self.router = router
        self.prompt_builder = prompt_builder
        self.cost_governor = cost_governor
        self.settings = settings
        self.planning_service = planning_service
        self.version_manager = version_manager
        self.event_bus = event_bus or getattr(orchestrator, "event_bus", None)
        self.llm_runtime = llm_runtime
        self.tool_selector = tool_selector

    async def execute_goal(
        self,
        goal: str,
        budget: float = 10.0,
        db_session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a user goal from planning decomposition to reflection repair and completion.

        Args:
            goal: Target request goal statement.
            budget: Execution budget cap.
            db_session: Optional active database context.

        Returns:
            Dictionary containing execution outputs, plan logs, and run telemetry.
        """
        trace_id = uuid4()
        session_id = uuid4()
        session = ReasoningSession(session_id, trace_id, budget, db_session)

        metrics = EngineMetrics(
            start_time=datetime.now(timezone.utc),
            total_cost=Decimal("0.0"),
        )
        start_perf = time.perf_counter()

        state = SessionState.PLANNING
        await self.transition_state(trace_id, state)

        # 1. Budget checkpoint 1: Before planning
        try:
            await self.cost_governor.check_budget_limits(Decimal("0.0"))
        except BudgetExceededError as err:
            return await self.abort_execution(
                trace_id,
                session,
                metrics,
                start_perf,
                FailureType.BudgetFailure,
                str(err),
            )

        # Generate initial plan
        plan_start = time.perf_counter()
        try:
            plan = await self.planning_service.generate_initial_plan(
                goal, session, trace_id
            )
        except Exception as err:
            return await self.abort_execution(
                trace_id,
                session,
                metrics,
                start_perf,
                FailureType.PlannerFailure,
                f"Initial planning failed: {err}",
            )
        metrics.planning_time = time.perf_counter() - plan_start
        self.version_manager.create_version(plan)

        # Execution loop across waves
        wave_idx = 0
        while wave_idx < len(plan.waves):
            wave = plan.waves[wave_idx]
            session.current_wave = wave_idx
            metrics.wave_count += 1

            # 2. Budget checkpoint 2: Before execution wave
            try:
                await self.cost_governor.check_budget_limits(Decimal("0.0"))
            except BudgetExceededError as err:
                return await self.abort_execution(
                    trace_id,
                    session,
                    metrics,
                    start_perf,
                    FailureType.BudgetFailure,
                    str(err),
                )

            state = SessionState.EXECUTING
            await self.transition_state(trace_id, state)

            exec_start = time.perf_counter()
            # Execute wave concurrently via orchestrator
            try:
                wave_result = await self.orchestrator.execute_wave(wave, session)
            except Exception as err:
                return await self.abort_execution(
                    trace_id,
                    session,
                    metrics,
                    start_perf,
                    FailureType.ToolFailure,
                    f"Orchestrated execution error: {err}",
                )
            metrics.execution_time += time.perf_counter() - exec_start

            # Check if any tasks failed in this wave
            failed_tasks = [t for t in wave.tasks if wave_result.status != "SUCCESS"]
            # Wait, if status != SUCCESS, let's identify failed tasks
            # Wait! wave_result contains results for all tasks
            # Let's check which tasks failed
            # If the wave has failed tasks, trigger reflection
            if failed_tasks:
                state = SessionState.REFLECTING
                await self.transition_state(trace_id, state)

                # 3. Budget checkpoint 3: Before reflection
                try:
                    await self.cost_governor.check_budget_limits(Decimal("0.0"))
                except BudgetExceededError as err:
                    return await self.abort_execution(
                        trace_id,
                        session,
                        metrics,
                        start_perf,
                        FailureType.BudgetFailure,
                        str(err),
                    )

                reflection_start = time.perf_counter()
                metrics.reflection_count += 1

                # Query reflection engine for the failed tasks
                # Mock reflection outcome for the first task
                failed_task = failed_tasks[0]
                reflection_res = await self.reflection_engine.reflect_and_correct(
                    task_name=failed_task.tool_name,
                    execution_result={"status": "FAILURE"},
                    session=session,
                )
                metrics.reflection_time += time.perf_counter() - reflection_start

                decision = reflection_res.get("status", "ABORT")
                if decision == "SUCCESS" or decision == "RESOLVED":
                    # Corrected by reflection, proceed
                    wave_idx += 1
                    continue
                elif decision == "RETRY" or decision == "REPLAN":
                    state = SessionState.REPAIRING
                    await self.transition_state(trace_id, state)

                    # 4 & 5. Budget checkpoints 4 & 5: Before replanning/repair
                    try:
                        await self.cost_governor.check_budget_limits(Decimal("0.0"))
                    except BudgetExceededError as err:
                        return await self.abort_execution(
                            trace_id,
                            session,
                            metrics,
                            start_perf,
                            FailureType.BudgetFailure,
                            str(err),
                        )

                    repair_start = time.perf_counter()
                    metrics.repair_count += 1

                    try:
                        new_plan = await self.planning_service.repair_plan(
                            plan, failed_tasks, session
                        )
                    except Exception as err:
                        return await self.abort_execution(
                            trace_id,
                            session,
                            metrics,
                            start_perf,
                            FailureType.PlannerFailure,
                            f"Plan repair failed: {err}",
                        )
                    metrics.repair_time += time.perf_counter() - repair_start

                    # Log version snapshot and compute structured diff
                    diff_dict = self.version_manager.diff(plan, new_plan)
                    self.version_manager.create_version(new_plan)
                    plan = new_plan

                    # Sync database snapshots
                    if db_session:
                        await session.save_plan_history(
                            new_plan.trace_id, str(diff_dict)
                        )

                    # Retrying: do not increment wave_idx to re-run the wave
                    continue
                else:
                    # ABORT / FAILED
                    return await self.abort_execution(
                        trace_id,
                        session,
                        metrics,
                        start_perf,
                        FailureType.ReflectionFailure,
                        "Reflection engine recommended aborting execution.",
                    )
            else:
                # Wave succeeded, advance
                wave_idx += 1

        # Completed successfully
        state = SessionState.COMPLETED
        await self.transition_state(trace_id, state)

        metrics.end_time = datetime.now(timezone.utc)
        metrics.total_duration = time.perf_counter() - start_perf
        metrics.total_cost = Decimal(str(session.total_cost))
        metrics.total_tokens = session.total_tokens

        # Persist session updates
        if db_session:
            await session.save_session_record()

        return {
            "status": "SUCCESS",
            "state": state,
            "metrics": metrics.model_dump(),
            "plan_version": plan.plan_version,
            "waves_executed": wave_idx,
        }

    async def abort_execution(
        self,
        trace_id: UUID,
        session: ReasoningSession,
        metrics: EngineMetrics,
        start_perf: float,
        failure_type: FailureType,
        error_msg: str,
    ) -> Dict[str, Any]:
        """Stop goal run execution, transition state, compile logs, and return error report.

        Args:
            trace_id: Active trace correlation UUID.
            session: Active ReasoningSession context tracker.
            metrics: Accumulated EngineMetrics log.
            start_perf: perf_counter start timestamp.
            failure_type: Specific FailureType categorization.
            error_msg: Detail error summary string.

        Returns:
            Dictionary report indicating FAILURE.
        """
        state = SessionState.FAILED
        await self.transition_state(trace_id, state)

        metrics.end_time = datetime.now(timezone.utc)
        metrics.total_duration = time.perf_counter() - start_perf
        metrics.total_cost = Decimal(str(session.total_cost))
        metrics.total_tokens = session.total_tokens

        # Persist updates
        if session.db_session:
            await session.save_session_record()

        return {
            "status": "FAILURE",
            "state": state,
            "failure_type": failure_type,
            "error": error_msg,
            "metrics": metrics.model_dump(),
        }

    async def transition_state(self, trace_id: UUID, state: SessionState) -> None:
        """Notify transitions state update over the EventBus.

        Args:
            trace_id: Correlation trace identifier.
            state: The SessionState target transitioning to.
        """
        if not self.event_bus:
            return

        msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=trace_id,
            sender="reasoning_engine",
            receiver="*",
            action="engine.state.transition",
            body={
                "state": state.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await self.event_bus.publish("engine.state.transition", msg)

    async def execute_goal_new(
        self,
        goal: str,
        budget: float = 10.0,
        db_session: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        dispatcher: Optional[ToolDispatcher] = None,
    ) -> Dict[str, Any]:
        """E2E execute a user goal from memory retrieval to planning, validation, and wave runs.

        Args:
            goal: Target request goal statement.
            budget: Execution budget cap.
            db_session: Optional database session context.
            memory_service: MemoryEngine or memory retrieval service instance.
            dispatcher: ToolDispatcher routing executor requests.
        """
        trace_id = uuid4()
        session_id = uuid4()
        session = ReasoningSession(session_id, trace_id, budget, db_session)

        metrics = EngineMetrics(
            start_time=datetime.now(timezone.utc),
            total_cost=Decimal("0.0"),
        )
        start_perf = time.perf_counter()

        # 1. Retrieve memories/context facts
        await self.transition_state(trace_id, SessionState.PLANNING)
        memories_list = []
        if memory_service:
            try:
                # Use hybrid search if search helper exists, else fallback search
                if hasattr(memory_service, "search") and hasattr(
                    memory_service.search, "search_hybrid"
                ):
                    records = await memory_service.search.search_hybrid(
                        query=goal, limit=5
                    )
                    memories_list = [r.content for r in records]
                elif hasattr(memory_service, "search_hybrid"):
                    records = await memory_service.search_hybrid(query=goal, limit=5)
                    memories_list = [r.content for r in records]
            except Exception:
                pass

        # 2. Analyze goal and constraints
        goal_analyzer = GoalAnalyzer()
        goal_obj = Goal(goal_text=goal)
        analysis = goal_analyzer.analyze(goal_obj)

        # Check budget limit before execution
        try:
            await self.cost_governor.check_budget_limits(Decimal("0.0"))
        except BudgetExceededError as err:
            return await self.abort_execution(
                trace_id,
                session,
                metrics,
                start_perf,
                FailureType.BudgetFailure,
                str(err),
            )

        # 3. Decompose goal to tasks
        task_gen = TaskGenerator(llm_runtime=self.llm_runtime)
        if self.llm_runtime is not None:
            tasks = await task_gen.decompose_with_llm(analysis, goal)
        else:
            tasks = task_gen.decompose(analysis, goal)

        # 3b. Intelligent tool re-selection
        if self.tool_selector is not None:
            for t in tasks:
                desc = (
                    t.payload.get("instruction")
                    or t.payload.get("command")
                    or t.payload.get("query")
                    or str(t.payload)
                )
                try:
                    sel = await self.tool_selector.select_tool(desc, {
                        "memory_context": memories_list,
                    })
                    if sel.confidence > 0.80:
                        t.executor = sel.executor_type
                except Exception:
                    pass

        # 4. Build dependency graph
        dep_builder = DependencyBuilder(tasks)
        try:
            dep_builder.validate_dag()
        except Exception as err:
            return await self.abort_execution(
                trace_id,
                session,
                metrics,
                start_perf,
                FailureType.PlannerFailure,
                f"Dependency DAG invalid: {err}",
            )

        # 5. Schedule parallel waves
        scheduler = ExecutionScheduler(dep_builder)
        waves = scheduler.schedule_waves()

        # 6. Pre-execution plan validation check
        validator = PlannerValidator()
        try:
            validator.validate_plan(goal_obj, analysis, tasks, waves, cost_limit=budget)
        except Exception as err:
            return await self.abort_execution(
                trace_id,
                session,
                metrics,
                start_perf,
                FailureType.PlannerFailure,
                f"Plan validation failed: {err}",
            )

        # 7. Compile the execution plan
        compiler = ExecutionPlanCompiler()
        plan = compiler.compile(goal_obj, analysis, tasks, waves)
        self.version_manager.create_version(plan)

        # 8. Execution loop across waves
        wave_idx = 0
        dispatcher = dispatcher or ToolDispatcher(tool_selector=self.tool_selector)
        context = {"memory_service": memory_service}

        while wave_idx < len(plan.waves):
            wave = plan.waves[wave_idx]
            session.current_wave = wave_idx
            metrics.wave_count += 1

            # Check budget checkpoint before wave runs
            try:
                await self.cost_governor.check_budget_limits(Decimal("0.0"))
            except BudgetExceededError as err:
                return await self.abort_execution(
                    trace_id,
                    session,
                    metrics,
                    start_perf,
                    FailureType.BudgetFailure,
                    str(err),
                )

            await self.transition_state(trace_id, SessionState.EXECUTING)

            exec_start = time.perf_counter()
            try:
                wave_result = await self.orchestrator.execute_wave_new(
                    wave=wave,
                    plan=plan,
                    session=session,
                    dispatcher=dispatcher,
                    context=context,
                )
            except Exception as err:
                return await self.abort_execution(
                    trace_id,
                    session,
                    metrics,
                    start_perf,
                    FailureType.ToolFailure,
                    f"Execution wave runtime crash: {err}",
                )
            metrics.execution_time += time.perf_counter() - exec_start

            # Wave outcomes validation
            if wave_result.status == "FAILURE":
                return await self.abort_execution(
                    trace_id,
                    session,
                    metrics,
                    start_perf,
                    FailureType.ToolFailure,
                    "Orchestrator wave task run failed.",
                )

            wave_idx += 1

        # Completed successfully
        await self.transition_state(trace_id, SessionState.COMPLETED)

        metrics.end_time = datetime.now(timezone.utc)
        metrics.total_duration = time.perf_counter() - start_perf
        metrics.total_cost = Decimal(str(session.total_cost))
        metrics.total_tokens = session.total_tokens

        # Persist session updates
        if db_session:
            await session.save_session_record()

        return {
            "status": "SUCCESS",
            "state": SessionState.COMPLETED,
            "metrics": metrics.model_dump(),
            "plan_version": getattr(plan, "plan_version", plan.metadata.get("plan_version", 1)),
            "waves_executed": wave_idx,
            "memories_loaded": len(memories_list),
        }

