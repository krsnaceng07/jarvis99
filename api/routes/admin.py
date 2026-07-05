"""
PHASE: 32
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api.dependencies import get_admin_manager, require_permissions
from api.dto import MetaBlock, SuccessEnvelope
from core.runtime.admin import AdminManager

# 1. Main router enforcing admin permission scope
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# =====================================================================
# Request & Response DTOs
# =====================================================================


class UpdateConfigPayload(BaseModel):
    """Schema for config live-updates."""

    system_log_level: Optional[str] = None
    sync_interval_seconds: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    telemetry_enabled: Optional[bool] = None


class ControlTaskPayload(BaseModel):
    """Schema for task running controls."""

    action: str  # pause, resume, cancel


class RestoreBackupPayload(BaseModel):
    """Schema for backups restoring payload."""

    backup_file: str


class VaultStatus(BaseModel):
    locked: bool
    initialized: bool


class ResourceUsage(BaseModel):
    disk_usage_percent: float
    cpu_load_percent: float
    memory_usage_percent: float


class DiagnosticsResponse(BaseModel):
    status: str
    database: str
    redis: str
    vault: VaultStatus
    resources: ResourceUsage


class MetricsResponse(BaseModel):
    uptime_seconds: float
    total_execution_runs: int
    completed_runs: int
    failed_runs: int
    success_rate: float
    daily_spent_usd: float


class ConfigResponse(BaseModel):
    system_log_level: str
    sync_interval_seconds: int
    rate_limit_per_minute: int
    telemetry_enabled: bool


class ConfigUpdateResponse(BaseModel):
    status: str
    config: ConfigResponse


class TaskControlResponse(BaseModel):
    status: str


class BackupCreateResponse(BaseModel):
    status: str
    backup_file: str


class BackupRestoreResponse(BaseModel):
    status: str


# =====================================================================
# Endpoints
# =====================================================================


@router.get(
    "/diagnostics", dependencies=[Depends(require_permissions(["platform.admin"]))]
)
async def get_diagnostics(
    request: Request,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """GET /api/v1/admin/diagnostics endpoint.

    Retrieves database, cache, and system health status.
    """
    res = await admin_manager.get_diagnostics()
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[DiagnosticsResponse](
        data=DiagnosticsResponse(**res), meta=meta
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.get("/metrics", dependencies=[Depends(require_permissions(["platform.admin"]))])
async def get_metrics(
    request: Request,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """GET /api/v1/admin/metrics endpoint.

    Retrieves system performance, latency and cost metrics.
    """
    res = await admin_manager.get_metrics()
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[MetricsResponse](data=MetricsResponse(**res), meta=meta)
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.get("/config", dependencies=[Depends(require_permissions(["platform.admin"]))])
async def get_config(
    request: Request,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """GET /api/v1/admin/config endpoint.

    Retrieves dynamic settings configurations.
    """
    res = await admin_manager.get_dynamic_config()
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[ConfigResponse](data=ConfigResponse(**res), meta=meta)
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post(
    "/config/update", dependencies=[Depends(require_permissions(["platform.admin"]))]
)
async def update_config(
    request: Request,
    payload: UpdateConfigPayload,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """POST /api/v1/admin/config/update endpoint.

    Live-updates transient dynamically configured parameters.
    """
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    res = await admin_manager.update_dynamic_config(updates)
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[ConfigUpdateResponse](
        data=ConfigUpdateResponse(**res), meta=meta
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post(
    "/tasks/{task_id}/control",
    dependencies=[Depends(require_permissions(["platform.admin"]))],
)
async def control_task(
    request: Request,
    task_id: str,
    payload: ControlTaskPayload,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """POST /api/v1/admin/tasks/{task_id}/control endpoint.

    Dispatches task loop control signals (pause, resume, cancel).
    """
    ok = await admin_manager.control_task(task_id, payload.action)
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[TaskControlResponse](
        data=TaskControlResponse(status="SUCCESS" if ok else "ERROR"), meta=meta
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post(
    "/backups/create", dependencies=[Depends(require_permissions(["platform.admin"]))]
)
async def create_backup(
    request: Request,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """POST /api/v1/admin/backups/create endpoint.

    Triggers database state serialization and saves JSON file to backup folder.
    """
    backup_file = await admin_manager.create_backup()
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[BackupCreateResponse](
        data=BackupCreateResponse(status="SUCCESS", backup_file=backup_file), meta=meta
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post(
    "/backups/restore", dependencies=[Depends(require_permissions(["platform.admin"]))]
)
async def restore_backup(
    request: Request,
    payload: RestoreBackupPayload,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """POST /api/v1/admin/backups/restore endpoint.

    Atomically replaces active database tables from JSON backup file.
    """
    ok = await admin_manager.restore_backup(payload.backup_file)
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[BackupRestoreResponse](
        data=BackupRestoreResponse(status="SUCCESS" if ok else "ERROR"), meta=meta
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.get("/dashboard")
async def get_dashboard(
    request: Request,
    token: Optional[str] = None,
    admin_manager: AdminManager = Depends(get_admin_manager),
) -> Response:
    """GET /api/v1/admin/dashboard endpoint.

    Serves the Single Page Application UI dashboard page.
    Enforces 'platform.admin' scope via Bearer token or Query parameter token.
    """
    auth_header = request.headers.get("Authorization")
    actual_token = None
    if auth_header and auth_header.startswith("Bearer "):
        actual_token = auth_header[7:]
    elif token:
        actual_token = token

    if not actual_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required. Accessible only by platform administrators.",
        )

    # Decode and verify token permissions
    from api.dependencies import get_kernel
    from core.security.jwt_service import JWTService

    kernel = get_kernel()
    try:
        jwt_service = kernel.container.resolve(JWTService)
        claims = jwt_service.verify_token(actual_token)
        permissions = claims.get("permissions", [])
        if "platform.admin" not in permissions:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Access is denied.",
            )
    except Exception as err:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired authorization token: {err}",
        )

    # Serve dashboard.html template
    template_path = os.path.join(
        os.path.dirname(__file__), "../templates/dashboard.html"
    )
    if not os.path.exists(template_path):
        template_path = "api/templates/dashboard.html"

    if not os.path.exists(template_path):
        raise HTTPException(
            status_code=404,
            detail="Dashboard HTML file template not found.",
        )

    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)
