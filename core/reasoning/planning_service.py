"""JARVIS OS - Planning Service.

Decouples plan decomposition and repair actions from the main execution engine.
"""

import time
from typing import List, Optional
from uuid import UUID, uuid4

from core.exceptions import JarvisSystemError
from core.reasoning.cost import CostGovernor
from core.reasoning.engine_dto import ExecutionPlan, RiskLevel
from core.reasoning.planner import ReasoningSession
from core.reasoning.prompt import PromptBuilder
from core.reasoning.router import ModelRouter
from core.tools.dto import ExecutionWave, WaveTask


class PlanningService:
    """Service wrapping LLM goal decomposition, token counting, and recovery planning."""

    def __init__(
        self,
        router: ModelRouter,
        prompt_builder: PromptBuilder,
        cost_governor: CostGovernor,
    ) -> None:
        """Initialize PlanningService.

        Args:
            router: ModelRouter connection.
            prompt_builder: Prompt compiling tool.
            cost_governor: Cost monitor gateway.
        """
        self.router = router
        self.prompt_builder = prompt_builder
        self.cost_governor = cost_governor

    async def generate_initial_plan(
        self,
        goal: str,
        session: ReasoningSession,
        trace_id: UUID,
        memories_list: Optional[List[str]] = None,
    ) -> ExecutionPlan:
        """Decompose a user request goal into sequential task waves.

        Args:
            goal: Target request instruction.
            session: Active ReasoningSession context tracker.
            trace_id: Session trace correlation ID.
            memories_list: Optional loaded context facts.

        Returns:
            ExecutionPlan DTO.
        """
        # 1. Budget checkpoint before planning
        provider = await self.router.get_provider_for_task("Planning")
        session.selected_model = provider.name

        compiled_prompt = self.prompt_builder.build_prompt(
            system_prompt="Decompose user goals into sequential waves.",
            user_goal=goal,
            memories=memories_list,
        )

        estimated_cost = self.cost_governor.estimate_cost(
            compiled_prompt, provider.name
        )
        await self.cost_governor.check_budget_limits(estimated_cost)

        # 2. Planning generation call
        start_t = time.perf_counter()
        raw_output = await provider.generate(compiled_prompt)
        session.latency_ms += (time.perf_counter() - start_t) * 1000.0

        # Calculate actual cost and usage
        in_tokens = provider.count_tokens(compiled_prompt)
        out_tokens = provider.count_tokens(raw_output)
        actual_cost = await self.cost_governor.log_usage(
            in_tokens, out_tokens, provider.name, provider.model_name
        )

        session.total_tokens += in_tokens + out_tokens
        session.total_cost += float(actual_cost)

        # Wave Decomposition Rules: Max 3 independent tasks per wave
        subtasks = [s.strip() for s in goal.split(",") if s.strip()]
        if not subtasks:
            subtasks = [goal]

        waves: List[ExecutionWave] = []
        current_tasks: List[WaveTask] = []
        wave_idx = 0

        for task_str in subtasks:
            wave_task = WaveTask(
                task_id=uuid4(),
                idempotency_key=uuid4(),
                tool_name="cmd_executor" if "run" in task_str else "file_writer",
                arguments={"command": [task_str]},
                priority=1,
                timeout=900.0,
                approval_level="L0",
                retry_policy=None,
                dependencies=[],
                metadata={},
            )
            current_tasks.append(wave_task)
            if len(current_tasks) == 3:
                waves.append(
                    ExecutionWave(
                        wave_id=uuid4(),
                        tasks=current_tasks,
                        status="PENDING",
                    )
                )
                current_tasks = []
                wave_idx += 1

        if current_tasks:
            waves.append(
                ExecutionWave(
                    wave_id=uuid4(),
                    tasks=current_tasks,
                    status="PENDING",
                )
            )

        # Strictly enforce Wave Rule check: no single wave can exceed 3 tasks
        for idx, w in enumerate(waves):
            if len(w.tasks) > 3:
                raise JarvisSystemError(
                    code="PLANNER_001",
                    message=f"Wave {idx} exceeds parallel task limit of 3.",
                )

        return ExecutionPlan(
            goal=goal,
            trace_id=trace_id,
            plan_version=1,
            waves=waves,
            estimated_cost=estimated_cost,
            estimated_tokens=in_tokens,
            risk_level=RiskLevel.MEDIUM if len(waves) > 2 else RiskLevel.LOW,
        )

    async def repair_plan(
        self,
        current_plan: ExecutionPlan,
        failed_tasks: List[WaveTask],
        session: ReasoningSession,
    ) -> ExecutionPlan:
        """Modify remaining waves to resolve execution bottlenecks and repair failure.

        Args:
            current_plan: Previous ExecutionPlan version state.
            failed_tasks: The tasks that failed execution in the last wave run.
            session: Active ReasoningSession.

        Returns:
            Repaired/Replanned ExecutionPlan DTO with incremented version.
        """
        # 1. Budget checkpoint before repair call
        provider = await self.router.get_provider_for_task("Planning")

        # Compile repair prompt context
        failures_desc = ", ".join(
            f"'{t.tool_name}' ({t.arguments})" for t in failed_tasks
        )
        repair_prompt = (
            f"Plan failed at tasks: {failures_desc}. Re-plan remaining steps."
        )

        compiled_prompt = self.prompt_builder.build_prompt(
            system_prompt="Repair the execution plan based on task failures.",
            user_goal=repair_prompt,
            memories=None,
        )

        estimated_cost = self.cost_governor.estimate_cost(
            compiled_prompt, provider.name
        )
        await self.cost_governor.check_budget_limits(estimated_cost)

        # 2. LLM Call
        start_t = time.perf_counter()
        raw_output = await provider.generate(compiled_prompt)
        session.latency_ms += (time.perf_counter() - start_t) * 1000.0

        # Calculate actual cost
        in_tokens = provider.count_tokens(compiled_prompt)
        out_tokens = provider.count_tokens(raw_output)
        actual_cost = await self.cost_governor.log_usage(
            in_tokens, out_tokens, provider.name, provider.model_name
        )

        session.total_tokens += in_tokens + out_tokens
        session.total_cost += float(actual_cost)

        # Compile new plan with updated version
        new_version = current_plan.plan_version + 1

        # Simply rebuild remaining waves and add a healing task
        rebuilt_waves: List[ExecutionWave] = []
        for wave in current_plan.waves:
            if wave.status in {"PENDING", "RUNNING"}:
                # Rebuild tasks
                healed_tasks = []
                for task in wave.tasks:
                    # Clear failed status and update parameters if failed
                    is_failed = any(ft.task_id == task.task_id for ft in failed_tasks)
                    healed_tasks.append(
                        WaveTask(
                            task_id=task.task_id if not is_failed else uuid4(),
                            idempotency_key=uuid4(),
                            tool_name=task.tool_name,
                            arguments={**task.arguments, "repaired": True}
                            if is_failed
                            else task.arguments,
                            priority=task.priority,
                            timeout=task.timeout,
                            approval_level=task.approval_level,
                            retry_policy=task.retry_policy,
                            dependencies=task.dependencies,
                            metadata={"replan_version": new_version},
                        )
                    )
                rebuilt_waves.append(
                    ExecutionWave(
                        wave_id=wave.wave_id,
                        tasks=healed_tasks,
                        status="PENDING",
                    )
                )
            else:
                rebuilt_waves.append(wave)

        return ExecutionPlan(
            goal=current_plan.goal,
            trace_id=current_plan.trace_id,
            plan_version=new_version,
            waves=rebuilt_waves,
            estimated_cost=current_plan.estimated_cost + estimated_cost,
            estimated_tokens=in_tokens,
            risk_level=RiskLevel.HIGH,
        )
