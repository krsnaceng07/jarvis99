"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

FastAPI APIRouter for Observability, Cost Governance & Live Execution Streaming.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)

from api.broadcaster import TelemetryBroadcaster
from api.dependencies import require_permissions
from core.observability.cost_governor import CostGovernor
from core.observability.dto import BudgetSummary, ComponentHealthRecord, TraceSpanRecord
from core.observability.health_probe import HealthProbe
from core.observability.metrics import PrometheusMetricsFormatter
from core.observability.span_repository import SpanRepository
from core.security.auth_context import RequestContext

logger = logging.getLogger("api.routes.observability")

observability_router = APIRouter(prefix="/api/v1/observability", tags=["observability"])
metrics_router = APIRouter(tags=["metrics"])
telemetry_ws_router = APIRouter(prefix="/ws/v1", tags=["observability"])

_span_repo: Optional[SpanRepository] = None
_cost_governor: Optional[CostGovernor] = None
_health_probe: Optional[HealthProbe] = None
_broadcaster: Optional[TelemetryBroadcaster] = None

JARVIS_TELEMETRY_AUTH_REQUIRED: bool = False


def set_observability_deps(
    span_repo: SpanRepository,
    cost_governor: CostGovernor,
    health_probe: HealthProbe,
    broadcaster: TelemetryBroadcaster,
    auth_required: bool = False,
) -> None:
    """Inject dependencies for observability routes."""
    global \
        _span_repo, \
        _cost_governor, \
        _health_probe, \
        _broadcaster, \
        JARVIS_TELEMETRY_AUTH_REQUIRED
    _span_repo = span_repo
    _cost_governor = cost_governor
    _health_probe = health_probe
    _broadcaster = broadcaster
    JARVIS_TELEMETRY_AUTH_REQUIRED = auth_required


def _get_span_repo() -> SpanRepository:
    if not _span_repo:
        raise HTTPException(status_code=503, detail="SpanRepository unavailable.")
    return _span_repo


def _get_cost_governor() -> CostGovernor:
    if not _cost_governor:
        raise HTTPException(status_code=503, detail="CostGovernor unavailable.")
    return _cost_governor


def _get_health_probe() -> HealthProbe:
    if not _health_probe:
        raise HTTPException(status_code=503, detail="HealthProbe unavailable.")
    return _health_probe


def _get_broadcaster() -> TelemetryBroadcaster:
    if not _broadcaster:
        raise HTTPException(status_code=503, detail="TelemetryBroadcaster unavailable.")
    return _broadcaster


@observability_router.get("/traces", response_model=list[TraceSpanRecord])
async def get_traces(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _ctx: RequestContext = Depends(require_permissions(["audit.read"])),
) -> list[TraceSpanRecord]:
    """Retrieve a paginated list of trace spans, newest first."""
    repo = _get_span_repo()
    return await repo.list_paginated(limit=limit, offset=offset)


@observability_router.get("/budget", response_model=BudgetSummary)
async def get_budget(
    _ctx: RequestContext = Depends(require_permissions(["audit.read"])),
) -> BudgetSummary:
    """Retrieve the daily and monthly budget usage summary."""
    gov = _get_cost_governor()
    return await gov.get_daily_summary()


@observability_router.get("/health", response_model=list[ComponentHealthRecord])
async def get_health(
    _ctx: RequestContext = Depends(require_permissions(["audit.read"])),
) -> list[ComponentHealthRecord]:
    """Retrieve all component health statuses."""
    probe = _get_health_probe()
    return await probe.get_health_records()


@metrics_router.get("/metrics")
async def get_prometheus_metrics() -> Any:
    """Expose application metrics in Prometheus text exposition format."""
    daily_cost = 0.0
    monthly_cost = 0.0
    health_ok = True

    if _cost_governor:
        try:
            summary = await _cost_governor.get_daily_summary()
            daily_cost = summary.daily_cost_usd
            monthly_cost = summary.monthly_cost_usd
        except Exception:
            pass

    if _health_probe:
        try:
            statuses = await _health_probe.get_health_status()
            health_ok = all(s == "ONLINE" for s in statuses.values())
        except Exception:
            pass

    metrics: Dict[str, Any] = {
        "jarvis_health_ok": {
            "value": health_ok,
            "type": "gauge",
            "help": "System health status (1 = healthy, 0 = degraded)",
        },
        "jarvis_daily_cost_usd": {
            "value": daily_cost,
            "type": "gauge",
            "help": "Total LLM API cost incurred today in USD",
        },
        "jarvis_monthly_cost_usd": {
            "value": monthly_cost,
            "type": "gauge",
            "help": "Total LLM API cost incurred this month in USD",
        },
    }

    from fastapi.responses import Response

    content = PrometheusMetricsFormatter.format_metrics(metrics)
    return Response(content=content, media_type="text/plain; version=0.0.4")


@telemetry_ws_router.websocket("/telemetry/stream")
async def telemetry_stream(
    websocket: WebSocket, token: Optional[str] = Query(default=None)
) -> None:
    """Real-time telemetry WebSocket streaming endpoint."""
    if JARVIS_TELEMETRY_AUTH_REQUIRED:
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return

        import hashlib

        from api.dependencies import get_kernel
        from core.exceptions import AuthenticationError
        from core.memory.database import db_manager
        from core.security.api_key_service import ApiKeyService
        from core.security.jwt_service import JWTService
        from core.security.rbac_service import RbacService
        from core.security.revocation_service import RevocationService
        from core.tools.security_repository import SecurityRepository

        kernel = get_kernel()
        authenticated = False
        permissions = []

        # 1. Try Bearer JWT Authentication
        try:
            jwt_service = kernel.container.resolve(JWTService)
            revocation_service = kernel.container.resolve(RevocationService)

            claims = jwt_service.verify_token(token)
            jti = claims.get("jti")

            # Check revocation status
            async with db_manager.session() as session:
                if jti and await revocation_service.is_token_revoked(jti, session):
                    raise AuthenticationError(code="AUTH_001", message="Token revoked")

            permissions = claims.get("permissions", [])
            authenticated = True
        except Exception:
            pass

        # 2. Try API Key Authentication if JWT failed
        if not authenticated:
            try:
                api_key_service = kernel.container.resolve(ApiKeyService)
                security_repository = kernel.container.resolve(SecurityRepository)
                rbac_service = kernel.container.resolve(RbacService)

                hashed_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
                async with db_manager.session() as session:
                    key_model = await security_repository.get_api_key_by_hashed(
                        hashed_key, session
                    )
                    if key_model and key_model.is_active:
                        if api_key_service.verify_api_key(token, key_model.hashed_key):
                            permissions = rbac_service.resolve_permissions(
                                key_model.user
                            )
                            authenticated = True
            except Exception:
                pass

        if not authenticated:
            await websocket.close(code=4001, reason="Unauthorized telemetry token")
            return

        # 3. Check authorization: require "audit.read" permission
        if "audit.read" not in permissions:
            await websocket.close(code=4003, reason="Forbidden")
            return

    broadcaster = _get_broadcaster()
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(websocket)
