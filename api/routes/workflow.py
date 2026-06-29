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

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_db_session,
    get_workflow_repository,
    get_workflow_validator,
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
from core.tools.compiler import WorkflowCompiler
from core.tools.repository import WorkflowRepository
from core.tools.validator import WorkflowValidator
from core.tools.workflow_dto import WorkflowPlan, WorkflowState

router = APIRouter()


@router.post("/workflows", status_code=202)
async def submit_workflow(
    request: Request,
    payload: WorkflowSubmitRequest,
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
    repository: WorkflowRepository = Depends(get_workflow_repository),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """GET /api/v1/workflows/{workflow_id} endpoint.

    Fetches the compilation status and state metrics of the specified workflow.
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

    # In Phase 14, workflow execution trigger is out of scope.
    # Therefore, status is always pending/ready.
    status_data = WorkflowStatusResponse(
        workflow_id=workflow_id,
        state=WorkflowState.PENDING,
        metrics=None,
    )

    envelope = SuccessEnvelope[WorkflowStatusResponse](data=status_data, meta=meta)
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
