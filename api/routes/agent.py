"""
PHASE: 14
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import uuid
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.dependencies import get_agent_runs, get_reasoning_engine
from api.dto import (
    AgentRunAcceptedResponse,
    AgentRunRequest,
    AgentRunStatusResponse,
    EngineMetrics,
    ErrorDetail,
    ErrorEnvelope,
    FailureType,
    MetaBlock,
    SessionState,
    SuccessEnvelope,
)
from core.reasoning.engine import ReasoningExecutionEngine

router = APIRouter()


async def run_agent_in_background(
    run_id: uuid.UUID,
    goal: str,
    budget: float,
    reasoning_engine: ReasoningExecutionEngine,
    agent_runs: Dict[uuid.UUID, AgentRunStatusResponse],
) -> None:
    """Background task executing the agent run and updating its lifecycle state."""
    agent_runs[run_id].state = SessionState.EXECUTING

    try:
        result = await reasoning_engine.execute_goal(goal=goal, budget=budget)
        status = result.get("status", "SUCCESS")
        metrics_dict = result.get("metrics", None)

        metrics = None
        if metrics_dict:
            metrics = EngineMetrics(**metrics_dict)

        failure_type = None
        if status != "SUCCESS":
            agent_runs[run_id].state = SessionState.FAILED
            failure_str = result.get("failure_type", None)
            if failure_str:
                try:
                    failure_type = FailureType(failure_str)
                except ValueError:
                    failure_type = FailureType.PlannerFailure
        else:
            agent_runs[run_id].state = SessionState.COMPLETED

        agent_runs[run_id].metrics = metrics
        agent_runs[run_id].failure_type = failure_type

    except Exception:
        agent_runs[run_id].state = SessionState.FAILED
        agent_runs[run_id].failure_type = FailureType.PlannerFailure


@router.post("/agent/run", status_code=202)
async def run_agent(
    request: Request,
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    reasoning_engine: ReasoningExecutionEngine = Depends(get_reasoning_engine),
    agent_runs: Dict[uuid.UUID, AgentRunStatusResponse] = Depends(get_agent_runs),
) -> Response:
    """POST /api/v1/agent/run endpoint.

    Schedules an asynchronous agent execution via FastAPI BackgroundTasks and
    immediately returns a 202 accepted response.
    """
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()

    # Initial status is PLANNING (queued/init state)
    status_response = AgentRunStatusResponse(
        run_id=run_id,
        state=SessionState.PLANNING,
    )
    agent_runs[run_id] = status_response

    # Schedule background worker execution
    background_tasks.add_task(
        run_agent_in_background,
        run_id=run_id,
        goal=payload.goal,
        budget=payload.budget,
        reasoning_engine=reasoning_engine,
        agent_runs=agent_runs,
    )

    accepted_data = AgentRunAcceptedResponse(
        run_id=run_id,
        trace_id=trace_id,
    )

    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        meta = MetaBlock(request_id=request_id)
    else:
        meta = MetaBlock()

    envelope = SuccessEnvelope[AgentRunAcceptedResponse](data=accepted_data, meta=meta)
    return JSONResponse(
        status_code=202,
        content=envelope.model_dump(mode="json"),
    )


@router.get("/agent/runs/{run_id}")
async def get_run_status(
    request: Request,
    run_id: uuid.UUID,
    agent_runs: Dict[uuid.UUID, AgentRunStatusResponse] = Depends(get_agent_runs),
) -> Response:
    """GET /api/v1/agent/runs/{run_id} endpoint.

    Retrieves in-memory status metrics and states for the specified run session.
    """
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        meta = MetaBlock(request_id=request_id)
    else:
        meta = MetaBlock()

    if run_id not in agent_runs:
        err_detail = ErrorDetail(
            code="RUN_NOT_FOUND",
            message=f"Agent run session with ID '{run_id}' was not found.",
        )
        err_envelope = ErrorEnvelope(error=err_detail, meta=meta)
        return JSONResponse(
            status_code=404,
            content=err_envelope.model_dump(mode="json"),
        )

    envelope = SuccessEnvelope[AgentRunStatusResponse](
        data=agent_runs[run_id], meta=meta
    )
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
