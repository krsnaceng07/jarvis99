"""JARVIS OS - Reasoning Session Planner.

Manages plan decomposition, structured PlanResult DTO validation, trace metrics logging, and database record mappings.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String

from core.exceptions import JarvisSystemError
from core.memory.models import Base
from core.reasoning.cost import CostGovernor
from core.reasoning.prompt import PromptBuilder
from core.reasoning.router import ModelRouter


class PlanResult(BaseModel):
    """Structured planning output detailing sequential execution wave tasks and metrics."""

    goal: str
    waves: List[List[str]]
    steps: List[str]
    dependencies: List[Dict[str, Any]] = Field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_tokens: int = 0
    confidence: float = 1.0
    requires_approval: bool = False


class ReasoningTrace(BaseModel):
    """Telemetry trace log for monitoring a single reasoning loop run."""

    session_id: UUID
    selected_model: str
    memory_loaded: bool = False
    plan_version: int = 1
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    reflection_attempts: int = 0
    termination_reason: str = "SUCCESS"
    total_tokens: int = 0
    total_cost: float = 0.0
    latency_ms: float = 0.0


class ReasoningSessionRecord(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a saved reasoning session's runtime variables."""

    __tablename__ = "user_reasoning_sessions"

    id = Column(String(36), primary_key=True)
    goal_id = Column(String(36), nullable=False, index=True)
    current_wave = Column(Integer, nullable=False, default=0)
    current_step = Column(Integer, nullable=False, default=0)
    selected_model = Column(String(100), nullable=True)
    budget = Column(Float, nullable=False, default=10.0)
    reflection_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class PlanHistory(Base):  # type: ignore[misc]
    """SQLAlchemy model tracking plan version revisions and execution outcomes."""

    __tablename__ = "user_plan_histories"

    id = Column(String(36), primary_key=True)
    goal_id = Column(String(36), nullable=False, index=True)
    plan_id = Column(String(36), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    planner_model = Column(String(100), nullable=True)
    execution_result = Column(String, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ReasoningSession:
    """Runtime instance of a reasoning session, coordinating prompts, plans, and trace logging."""

    def __init__(
        self,
        session_id: UUID,
        goal_id: UUID,
        budget: float = 10.0,
        db_session: Optional[Any] = None,
    ) -> None:
        """Initialize ReasoningSession.

        Args:
            session_id: Session ID UUID.
            goal_id: Target goal ID UUID.
            budget: Session budget constraint.
            db_session: Optional database session.
        """
        self.session_id = session_id
        self.goal_id = goal_id
        self.current_wave = 0
        self.current_step = 0
        self.selected_model: Optional[str] = None
        self.budget = budget
        self.reflection_count = 0
        self.plan_version = 1
        self.db_session = db_session

        # Telemetry metrics
        self.tool_calls: List[Dict[str, Any]] = []
        self.memory_loaded = False
        self.total_tokens = 0
        self.total_cost = 0.0
        self.latency_ms = 0.0

    async def save_session_record(self) -> None:
        """Persist/Update session state variables inside SQL database."""
        if not self.db_session:
            return

        record = ReasoningSessionRecord(
            id=str(self.session_id),
            goal_id=str(self.goal_id),
            current_wave=self.current_wave,
            current_step=self.current_step,
            selected_model=self.selected_model,
            budget=self.budget,
            reflection_count=self.reflection_count,
            created_at=datetime.now(timezone.utc),
        )
        self.db_session.add(record)
        await self.db_session.flush()

    async def save_plan_history(self, plan_id: UUID, result: str) -> None:
        """Log a plan revision snapshot to the historical registry database.

        Args:
            plan_id: Unique plan UUID.
            result: Detailed generated checklist description.
        """
        if not self.db_session:
            return

        history = PlanHistory(
            id=str(uuid4()),
            goal_id=str(self.goal_id),
            plan_id=str(plan_id),
            version=self.plan_version,
            planner_model=self.selected_model,
            execution_result=result,
            created_at=datetime.now(timezone.utc),
        )
        self.db_session.add(history)
        await self.db_session.flush()

    async def decompose_goal(
        self,
        goal: str,
        prompt_builder: PromptBuilder,
        router: ModelRouter,
        cost_gov: CostGovernor,
        memories_list: Optional[List[str]] = None,
    ) -> PlanResult:
        """Decompose goal query statement into parallel wave subtasks.

        Args:
            goal: Target request instruction.
            prompt_builder: PromptBuilder instance.
            router: ModelRouter instance.
            cost_gov: CostGovernor instance.
            memories_list: Optional loaded context facts.

        Returns:
            PlanResult DTO mapping waves and estimates.
        """
        # Resolve target provider
        provider = await router.get_provider_for_task("Planning")
        self.selected_model = provider.name
        self.memory_loaded = bool(memories_list)

        # Assemble prompt context
        compiled_prompt = prompt_builder.build_prompt(
            system_prompt="Decompose user goals into sequential waves.",
            user_goal=goal,
            memories=memories_list,
        )

        # Cost estimation and budget checking
        estimated_cost = cost_gov.estimate_cost(compiled_prompt, provider.name)
        await cost_gov.check_budget_limits(estimated_cost)

        # Run provider generation
        import time

        start_t = time.perf_counter()
        raw_output = await provider.generate(compiled_prompt)
        duration_ms = (time.perf_counter() - start_t) * 1000.0
        self.latency_ms += duration_ms

        # Compute cost metrics
        in_tokens = provider.count_tokens(compiled_prompt)
        out_tokens = provider.count_tokens(raw_output)
        actual_cost = await cost_gov.log_usage(
            in_tokens, out_tokens, provider.name, provider.model_name
        )

        self.total_tokens += in_tokens + out_tokens
        self.total_cost += float(actual_cost)

        # Wave Decomposition Rules: Max 3 independent tasks per wave, atomic checklist
        # For mock purposes, split goal sentences to populate waves
        subtasks = [s.strip() for s in goal.split(",") if s.strip()]
        if not subtasks:
            subtasks = [goal]

        # Group into waves of max 3 tasks
        waves: List[List[str]] = []
        current_wave_group: List[str] = []
        for task in subtasks:
            current_wave_group.append(task)
            if len(current_wave_group) == 3:
                waves.append(current_wave_group)
                current_wave_group = []
        if current_wave_group:
            waves.append(current_wave_group)

        # Strictly enforce Wave Rule check: no single wave can exceed 3 tasks
        for idx, w in enumerate(waves):
            if len(w) > 3:
                raise JarvisSystemError(
                    code="PLANNER_001",
                    message=f"Wave {idx} exceeds parallel task limit of 3.",
                )

        plan_id = uuid4()
        plan_result = PlanResult(
            goal=goal,
            waves=waves,
            steps=[f"Step: {t}" for w in waves for t in w],
            dependencies=[],
            estimated_cost=float(estimated_cost),
            estimated_tokens=in_tokens,
            confidence=0.95,
            requires_approval=(estimated_cost > cost_gov.per_call_budget),
        )

        # Persist results
        await self.save_session_record()
        await self.save_plan_history(plan_id, str(plan_result.waves))

        return plan_result

    def generate_trace(self, termination_reason: str = "SUCCESS") -> ReasoningTrace:
        """Compile accumulated telemetry properties into a trace log DTO.

        Args:
            termination_reason: Final session status description.

        Returns:
            ReasoningTrace DTO.
        """
        return ReasoningTrace(
            session_id=self.session_id,
            selected_model=self.selected_model or "unknown",
            memory_loaded=self.memory_loaded,
            plan_version=self.plan_version,
            tool_calls=self.tool_calls,
            reflection_attempts=self.reflection_count,
            termination_reason=termination_reason,
            total_tokens=self.total_tokens,
            total_cost=self.total_cost,
            latency_ms=self.latency_ms,
        )
