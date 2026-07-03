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

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_db_session,
    get_execution_repository,
    get_reasoning_engine,
    require_permissions,
)
from api.dto import (
    AgentRunAcceptedResponse,
    AgentRunRequest,
    AgentRunsHistoryResponse,
    AgentRunStatusResponse,
    EngineMetrics,
    ErrorDetail,
    ErrorEnvelope,
    FailureType,
    MetaBlock,
    SessionState,
    SuccessEnvelope,
)
from core.memory.database import db_manager
from core.reasoning.engine import ReasoningExecutionEngine
from core.reasoning.persistence_service import active_run_id
from core.security.auth_context import RequestContext
from core.tools.execution_repository import ExecutionRepository

router = APIRouter()


async def run_agent_in_background(
    run_id: uuid.UUID,
    goal: str,
    budget: float,
    reasoning_engine: ReasoningExecutionEngine,
    repository: ExecutionRepository,
) -> None:
    """Background task executing the agent run and updating its persistent state."""
    # Set the ContextVar for the persistence service to associate telemetry trace with this run
    active_run_id.set(run_id)

    async with db_manager.session() as session:
        async with session.begin():
            await repository.update_agent_run_state(
                run_id=run_id,
                state=SessionState.EXECUTING.value,
                session=session,
            )

    try:
        result = await reasoning_engine.execute_goal(goal=goal, budget=budget)
        status = result.get("status", "SUCCESS")
        metrics_dict = result.get("metrics", None)

        metrics = None
        if metrics_dict:
            metrics = EngineMetrics(**metrics_dict)

        failure_type = None
        if status != "SUCCESS":
            state = SessionState.FAILED
            failure_str = result.get("failure_type", None)
            if failure_str:
                try:
                    failure_type = FailureType(failure_str)
                except ValueError:
                    failure_type = FailureType.PlannerFailure
        else:
            state = SessionState.COMPLETED

        async with db_manager.session() as session:
            async with session.begin():
                await repository.update_agent_run_state(
                    run_id=run_id,
                    state=state.value,
                    metrics=metrics.model_dump(mode="json") if metrics else None,
                    failure_type=failure_type.value if failure_type else None,
                    session=session,
                )

    except Exception:
        async with db_manager.session() as session:
            async with session.begin():
                await repository.update_agent_run_state(
                    run_id=run_id,
                    state=SessionState.FAILED.value,
                    failure_type=FailureType.PlannerFailure.value,
                    session=session,
                )


@router.post("/agent/run", status_code=202)
async def run_agent(
    request: Request,
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    _ctx: RequestContext = Depends(require_permissions(["agent.execute"])),
    reasoning_engine: ReasoningExecutionEngine = Depends(get_reasoning_engine),
    repository: ExecutionRepository = Depends(get_execution_repository),
) -> Response:
    """POST /api/v1/agent/run endpoint.

    Schedules an asynchronous agent execution via FastAPI BackgroundTasks and
    immediately returns a 202 accepted response, writing the initial run log to the DB.
    """
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()

    async with db_manager.session() as session:
        async with session.begin():
            await repository.save_agent_run(
                run_id=run_id,
                goal=payload.goal,
                budget=payload.budget,
                state=SessionState.PLANNING.value,
                session=session,
            )

    background_tasks.add_task(
        run_agent_in_background,
        run_id=run_id,
        goal=payload.goal,
        budget=payload.budget,
        reasoning_engine=reasoning_engine,
        repository=repository,
    )

    accepted_data = AgentRunAcceptedResponse(
        run_id=run_id,
        trace_id=trace_id,
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id is not None else MetaBlock()

    envelope = SuccessEnvelope[AgentRunAcceptedResponse](data=accepted_data, meta=meta)
    return JSONResponse(
        status_code=202,
        content=envelope.model_dump(mode="json"),
    )


@router.get("/agent/runs/{run_id}")
async def get_run_status(
    request: Request,
    run_id: uuid.UUID,
    _ctx: RequestContext = Depends(require_permissions(["agent.read"])),
    repository: ExecutionRepository = Depends(get_execution_repository),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    """GET /api/v1/agent/runs/{run_id} endpoint.

    Retrieves database status metrics and states for the specified run session.
    """
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id is not None else MetaBlock()

    run_model = await repository.get_agent_run(run_id, db_session)
    if run_model is None:
        err_detail = ErrorDetail(
            code="RUN_NOT_FOUND",
            message=f"Agent run session with ID '{run_id}' was not found.",
        )
        err_envelope = ErrorEnvelope(error=err_detail, meta=meta)
        return JSONResponse(
            status_code=404,
            content=err_envelope.model_dump(mode="json"),
        )

    metrics_data = None
    if run_model.metrics:
        metrics_data = EngineMetrics(**run_model.metrics)

    status_data = AgentRunStatusResponse(
        run_id=run_model.id,
        state=SessionState(run_model.state),
        metrics=metrics_data,
        failure_type=FailureType(run_model.failure_type)
        if run_model.failure_type
        else None,
    )

    envelope = SuccessEnvelope[AgentRunStatusResponse](data=status_data, meta=meta)
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )


@router.get("/agent/runs")
async def list_runs(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    _ctx: RequestContext = Depends(require_permissions(["agent.read"])),
    repository: ExecutionRepository = Depends(get_execution_repository),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    """GET /api/v1/agent/runs endpoint for history query (Phase 15)."""
    runs_models = await repository.list_agent_runs(limit, offset, db_session)

    data_list = []
    for run in runs_models:
        metrics_data = None
        if run.metrics:
            metrics_data = EngineMetrics(**run.metrics)
        data_list.append(
            AgentRunStatusResponse(
                run_id=run.id,
                state=SessionState(run.state),
                metrics=metrics_data,
                failure_type=FailureType(run.failure_type)
                if run.failure_type
                else None,
            )
        )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id is not None else MetaBlock()

    runs_history = AgentRunsHistoryResponse(runs=data_list)
    envelope = SuccessEnvelope[AgentRunsHistoryResponse](data=runs_history, meta=meta)
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
