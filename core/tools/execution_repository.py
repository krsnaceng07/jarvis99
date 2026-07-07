"""
PHASE: 15
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.tools.execution_models import (
    AgentRunModel,
    WorkflowExecutionModel,
    WorkflowStepExecutionModel,
)


class ExecutionRepository:
    """Manages pure CRUD operations for agent runs and workflow executions in the database."""

    async def create_tables(self, session: AsyncSession) -> None:
        """Create database tables dynamically if they do not exist."""
        bind = session.bind
        if bind:
            from typing import cast

            from core.memory.models import Base

            async with cast(Any, bind).connect() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def save_agent_run(
        self,
        run_id: UUID,
        goal: str,
        budget: float,
        state: str,
        session: AsyncSession,
    ) -> None:
        """Create or update an agent run record in the database."""
        q = select(AgentRunModel).where(AgentRunModel.id == run_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model:
            model = AgentRunModel(
                id=run_id,
                goal=goal,
                budget=budget,
                state=state,
            )
            session.add(model)
        else:
            model.goal = goal
            model.budget = budget
            model.state = state

    async def update_agent_run_state(
        self,
        run_id: UUID,
        state: str,
        session: AsyncSession,
        metrics: Optional[dict] = None,
        failure_type: Optional[str] = None,
    ) -> None:
        """Update active state, metrics, and failure metadata for an agent run."""
        q = select(AgentRunModel).where(AgentRunModel.id == run_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if model:
            model.state = state
            if metrics is not None:
                model.metrics = metrics
            if failure_type is not None:
                model.failure_type = failure_type

    async def get_agent_run(
        self, run_id: UUID, session: AsyncSession
    ) -> Optional[AgentRunModel]:
        """Retrieve an agent run record by its unique ID."""
        q = select(AgentRunModel).where(AgentRunModel.id == run_id)
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def list_agent_runs(
        self, limit: int, offset: int, session: AsyncSession
    ) -> List[AgentRunModel]:
        """Fetch historical agent run statuses sorted by creation timestamp descending."""
        q = (
            select(AgentRunModel)
            .order_by(AgentRunModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(q)
        return list(res.scalars().all())

    async def save_workflow_execution(
        self,
        execution_id: UUID,
        workflow_id: UUID,
        version: int,
        state: str,
        session: AsyncSession,
    ) -> None:
        """Initialize or update a workflow execution run record."""
        q = select(WorkflowExecutionModel).where(
            WorkflowExecutionModel.id == execution_id
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model:
            model = WorkflowExecutionModel(
                id=execution_id,
                workflow_id=workflow_id,
                version=version,
                state=state,
            )
            session.add(model)
        else:
            model.workflow_id = workflow_id
            model.version = version
            model.state = state

    async def update_workflow_execution(
        self,
        execution_id: UUID,
        state: str,
        session: AsyncSession,
        metrics: Optional[dict] = None,
    ) -> None:
        """Update status state and aggregated metrics of a workflow execution."""
        q = select(WorkflowExecutionModel).where(
            WorkflowExecutionModel.id == execution_id
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if model:
            model.state = state
            if metrics is not None:
                model.metrics = metrics

    async def get_workflow_execution(
        self, execution_id: UUID, session: AsyncSession
    ) -> Optional[WorkflowExecutionModel]:
        """Retrieve workflow execution status record by its unique ID."""
        q = select(WorkflowExecutionModel).where(
            WorkflowExecutionModel.id == execution_id
        )
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def get_latest_workflow_execution(
        self, workflow_id: UUID, session: AsyncSession
    ) -> Optional[WorkflowExecutionModel]:
        """Fetch the latest workflow execution run for a given workflow ID."""
        q = (
            select(WorkflowExecutionModel)
            .where(WorkflowExecutionModel.workflow_id == workflow_id)
            .order_by(WorkflowExecutionModel.created_at.desc())
            .limit(1)
        )
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def save_step_execution(
        self,
        execution_id: UUID,
        step_name: str,
        state: str,
        attempts: int,
        session: AsyncSession,
        output: Optional[dict] = None,
        error: Optional[dict] = None,
    ) -> None:
        """Create or update a step execution log."""
        q = select(WorkflowStepExecutionModel).where(
            (WorkflowStepExecutionModel.execution_id == execution_id)
            & (WorkflowStepExecutionModel.step_name == step_name)
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model:
            model = WorkflowStepExecutionModel(
                execution_id=execution_id,
                step_name=step_name,
                state=state,
                attempts=attempts,
                output=output,
                error=error,
            )
            session.add(model)
        else:
            model.state = state
            model.attempts = attempts
            if output is not None:
                model.output = output
            if error is not None:
                model.error = error

    async def get_step_executions(
        self, execution_id: UUID, session: AsyncSession
    ) -> List[WorkflowStepExecutionModel]:
        """Retrieve all step execution details for a specific workflow run."""
        q = select(WorkflowStepExecutionModel).where(
            WorkflowStepExecutionModel.execution_id == execution_id
        )
        res = await session.execute(q)
        return list(res.scalars().all())

    async def get_active_agent_run_ids(self, session: AsyncSession) -> List[UUID]:
        """Fetches run_ids of agent runs stuck in planning or executing states."""
        q = select(AgentRunModel.id).where(
            AgentRunModel.state.in_(["Planning", "Executing"])
        )
        res = await session.execute(q)
        return list(res.scalars().all())

    async def get_active_workflow_run_ids(self, session: AsyncSession) -> List[UUID]:
        """Fetches run_ids of workflow runs stuck in running states."""
        q = select(WorkflowExecutionModel.id).where(
            WorkflowExecutionModel.state.in_(["RUNNING"])
        )
        res = await session.execute(q)
        return list(res.scalars().all())
