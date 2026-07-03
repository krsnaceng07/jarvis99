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

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_db_session,
    get_execution_repository,
    get_workflow_repository,
    get_workflow_validator,
    require_permissions,
)
from api.dto import (
    ErrorDetail,
    ErrorEnvelope,
    MetaBlock,
    SuccessEnvelope,
    WorkflowStatusResponse,
    WorkflowSubmitRequest,
    WorkflowSubmitResponse,
)
from core.security.auth_context import RequestContext
from core.tools.compiler import WorkflowCompiler
from core.tools.execution_repository import ExecutionRepository
from core.tools.repository import WorkflowRepository
from core.tools.validator import WorkflowValidator
from core.tools.workflow_dto import WorkflowPlan, WorkflowState

router = APIRouter()


@router.post("/workflows", status_code=202)
async def submit_workflow(
    request: Request,
    payload: WorkflowSubmitRequest,
    _ctx: RequestContext = Depends(require_permissions(["workflow.execute"])),
    validator: WorkflowValidator = Depends(get_workflow_validator),
    repository: WorkflowRepository = Depends(get_workflow_repository),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """POST /api/v1/workflows endpoint.

    Validates, compiles, and persists a new workflow plan config, returning a
    202 accepted response carrying the new workflow metadata.
    """
    workflow_id = uuid.uuid4()
    plan = WorkflowPlan(
        name=payload.name,
        workflow_id=workflow_id,
        steps=payload.steps,
        version=payload.version,
    )

    # 1. Validate WorkflowPlan structure & tool bindings
    validator.validate(plan)

    # 2. Compile reference DAG and verify wave sorts
    compiler = WorkflowCompiler()
    compiler.compile(plan)

    # 3. Save to database repository
    saved_ver = await repository.save(plan=plan, session=session)

    submit_data = WorkflowSubmitResponse(
        workflow_id=saved_ver.workflow_id,
        version=saved_ver.version,
        status=WorkflowState.PENDING,
    )

    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        meta = MetaBlock(request_id=request_id)
    else:
        meta = MetaBlock()

    envelope = SuccessEnvelope[WorkflowSubmitResponse](data=submit_data, meta=meta)
    return JSONResponse(
        status_code=202,
        content=envelope.model_dump(mode="json"),
    )


@router.get("/workflows/{workflow_id}")
async def get_workflow_status(
    request: Request,
    workflow_id: uuid.UUID,
    _ctx: RequestContext = Depends(require_permissions(["workflow.read"])),
    repository: WorkflowRepository = Depends(get_workflow_repository),
    exec_repository: ExecutionRepository = Depends(get_execution_repository),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """GET /api/v1/workflows/{workflow_id} endpoint.

    Fetches the compilation status and state metrics of the specified workflow.
    Phase 15 upgrade: queries the latest execution record from the database.
    """
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        meta = MetaBlock(request_id=request_id)
    else:
        meta = MetaBlock()

    # Retrieve from repository database
    plan = await repository.get(workflow_id=workflow_id, session=session)

    if plan is None:
        err_detail = ErrorDetail(
            code="WORKFLOW_NOT_FOUND",
            message=f"Workflow configuration with ID '{workflow_id}' was not found.",
        )
        err_envelope = ErrorEnvelope(error=err_detail, meta=meta)
        return JSONResponse(
            status_code=404,
            content=err_envelope.model_dump(mode="json"),
        )

    # Phase 15: query latest execution from persistence layer
    latest_exec = await exec_repository.get_latest_workflow_execution(
        workflow_id, session
    )

    if latest_exec is not None:
        state = WorkflowState(latest_exec.state)
        metrics = None
        if latest_exec.metrics:
            from core.tools.workflow_dto import WorkflowMetrics

            metrics = WorkflowMetrics(**latest_exec.metrics)
    else:
        state = WorkflowState.PENDING
        metrics = None

    status_data = WorkflowStatusResponse(
        workflow_id=workflow_id,
        state=state,
        metrics=metrics,
    )

    envelope = SuccessEnvelope[WorkflowStatusResponse](data=status_data, meta=meta)
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
