"""
PHASE: 35
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_scale_manager
from api.dto import ErrorDetail, ErrorEnvelope, MetaBlock, SuccessEnvelope
from api.routes.federation import verify_federation_signature

router = APIRouter()


class TaskOffloadPayload(BaseModel):
    code: str
    callback_url: Optional[str] = None


class TaskOffloadRequest(BaseModel):
    task_id: str
    type: str
    payload: TaskOffloadPayload


class TaskOffloadResponse(BaseModel):
    status: str
    task_id: str
    node_id: str


class RemoteToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]


class RemoteToolExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int


class NodeLoadMetricsResponse(BaseModel):
    cpu_usage: float
    memory_usage: float
    active_tasks: int


class TaskCallbackRequest(BaseModel):
    task_id: str
    status: str
    node_id: str
    stdout: str
    stderr: str
    exit_code: int


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    node_id: str
    stdout: str
    stderr: str
    exit_code: int


@router.post("/federation/offload", dependencies=[Depends(verify_federation_signature)])
async def offload_task(
    request: Request,
    body: TaskOffloadRequest,
    scale_mgr: Any = Depends(get_scale_manager),
) -> Response:
    """POST /api/v1/federation/offload

    Accepts task offload requests from federated nodes and schedules background execution.
    """
    if body.type != "execute_code":
        request_id = getattr(request.state, "request_id", uuid4())
        meta = MetaBlock(request_id=request_id)
        detail = ErrorDetail(
            code="VALIDATION_ERROR",
            message="Unsupported offload type. Only 'execute_code' is supported.",
        )
        err_envelope = ErrorEnvelope(error=detail, meta=meta)
        return JSONResponse(status_code=400, content=err_envelope.model_dump(mode="json"))

    sender_node_id = request.headers.get("X-Jarvis-Node-Id")

    # 1. Register task status as QUEUED
    local_node_id = getattr(scale_mgr.federation_manager, "node_id", "node_default")
    scale_mgr._offloaded_tasks[body.task_id] = {
        "task_id": body.task_id,
        "status": "QUEUED",
        "node_id": local_node_id,
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    # 2. Spawn background sandbox executor task
    asyncio.create_task(
        scale_mgr.run_offloaded_task_background(
            task_id=body.task_id,
            code=body.payload.code,
            sender_node_id=sender_node_id,
            callback_url=body.payload.callback_url,
        )
    )

    data = TaskOffloadResponse(
        status="QUEUED", task_id=body.task_id, node_id=local_node_id
    )
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[TaskOffloadResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post(
    "/federation/tools/execute", dependencies=[Depends(verify_federation_signature)]
)
async def execute_remote_tool(
    request: Request,
    body: RemoteToolExecuteRequest,
    scale_mgr: Any = Depends(get_scale_manager),
) -> Response:
    """POST /api/v1/federation/tools/execute

    Delegates tool execution to local sandbox strictly, preventing host direct access.
    """
    if body.tool_name != "python_sandbox":
        request_id = getattr(request.state, "request_id", uuid4())
        meta = MetaBlock(request_id=request_id)
        detail = ErrorDetail(
            code="AUTH_006",
            message="Tool execution forbidden. Only 'python_sandbox' tool execution is allowed remotely.",
        )
        err_envelope = ErrorEnvelope(error=detail, meta=meta)
        return JSONResponse(status_code=403, content=err_envelope.model_dump(mode="json"))

    code = body.arguments.get("code")
    if not code:
        request_id = getattr(request.state, "request_id", uuid4())
        meta = MetaBlock(request_id=request_id)
        detail = ErrorDetail(
            code="VALIDATION_ERROR",
            message="Missing 'code' argument for python_sandbox tool execution.",
        )
        err_envelope = ErrorEnvelope(error=detail, meta=meta)
        return JSONResponse(status_code=400, content=err_envelope.model_dump(mode="json"))

    try:
        # Execute tool strictly inside sandbox
        res = await scale_mgr.local_sandbox.run(
            image="python:3.12-slim", command=["python", "-c", code], timeout=30.0
        )
        exit_code = res.get("exit_code", 0)
        data = RemoteToolExecuteResponse(
            success=(exit_code == 0),
            stdout=res.get("stdout", ""),
            stderr=res.get("stderr", ""),
            exit_code=exit_code,
        )
    except Exception as e:
        data = RemoteToolExecuteResponse(
            success=False,
            stdout="",
            stderr=f"Tool execution failed: {str(e)}",
            exit_code=-1,
        )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[RemoteToolExecuteResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.get("/federation/load", dependencies=[Depends(verify_federation_signature)])
async def get_node_load(
    request: Request,
    scale_mgr: Any = Depends(get_scale_manager),
) -> Response:
    """GET /api/v1/federation/load

    Returns node performance load metrics.
    """
    metrics = await scale_mgr.get_node_load_metrics()
    data = NodeLoadMetricsResponse(
        cpu_usage=metrics.get("cpu_usage", 0.0),
        memory_usage=metrics.get("memory_usage", 0.0),
        active_tasks=metrics.get("active_tasks", 0),
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[NodeLoadMetricsResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


class SimpleSuccessResponse(BaseModel):
    status: str = "success"


@router.post(
    "/federation/offload/callback", dependencies=[Depends(verify_federation_signature)]
)
async def task_offload_callback(
    request: Request,
    body: TaskCallbackRequest,
    scale_mgr: Any = Depends(get_scale_manager),
) -> Response:
    """POST /api/v1/federation/offload/callback

    Accepts task completion status report callback from remote worker node.
    """
    # Store callback result status in local scale manager status dictionary
    scale_mgr._offloaded_tasks[body.task_id] = {
        "task_id": body.task_id,
        "status": body.status,
        "node_id": body.node_id,
        "stdout": body.stdout,
        "stderr": body.stderr,
        "exit_code": body.exit_code,
    }

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[SimpleSuccessResponse](
        data=SimpleSuccessResponse(status="success"), meta=meta
    )
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.get(
    "/federation/offload/{task_id}/result",
    dependencies=[Depends(verify_federation_signature)],
)
async def get_task_result(
    request: Request,
    task_id: str,
    scale_mgr: Any = Depends(get_scale_manager),
) -> Response:
    """GET /api/v1/federation/offload/{task_id}/result

    Queries execution outcome or status of an offloaded task.
    """
    task = scale_mgr._offloaded_tasks.get(task_id)
    if not task:
        request_id = getattr(request.state, "request_id", uuid4())
        meta = MetaBlock(request_id=request_id)
        detail = ErrorDetail(
            code="SYSTEM_001",
            message=f"Task {task_id} not found in this node's offloaded list.",
        )
        err_envelope = ErrorEnvelope(error=detail, meta=meta)
        return JSONResponse(status_code=404, content=err_envelope.model_dump(mode="json"))

    data = TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        node_id=task["node_id"],
        stdout=task["stdout"],
        stderr=task["stderr"],
        exit_code=task["exit_code"],
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[TaskStatusResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))
