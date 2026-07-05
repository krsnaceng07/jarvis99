"""
PHASE: 33
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/d42af1e8-69f8-4bf2-a03f-dc029da887c0/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import os
from typing import Any, Dict, cast

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_deployment_health_manager, require_permissions

router = APIRouter(tags=["platform"])


@router.get("/api/v1/platform/status")
async def get_status(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    health_mgr: Any = Depends(get_deployment_health_manager),
) -> Dict[str, Any]:
    """Retrieve basic environment status information. Protected by platform.admin."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": os.getenv("JARVIS_SYSTEM_ENVIRONMENT", "production"),
    }


@router.get("/api/v1/platform/liveness")
async def get_liveness(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    health_mgr: Any = Depends(get_deployment_health_manager),
) -> Dict[str, Any]:
    """Shallow liveness check. Protected by platform.admin."""
    return cast(Dict[str, Any], await health_mgr.check_liveness())


@router.get("/api/v1/platform/readiness")
async def get_readiness(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    health_mgr: Any = Depends(get_deployment_health_manager),
) -> Dict[str, Any]:
    """Deep readiness check validating databases and vault decryption. Protected by platform.admin."""
    res = cast(Dict[str, Any], await health_mgr.check_readiness())
    if res["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=res,
        )
    return res


@router.post("/api/v1/platform/preflight")
async def run_preflight(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    health_mgr: Any = Depends(get_deployment_health_manager),
) -> Dict[str, Any]:
    """Execute dynamic preflight checks on dependencies. Protected by platform.admin."""
    return cast(Dict[str, Any], await health_mgr.run_preflight_checks())


@router.get("/api/v1/platform/deployment")
async def get_deployment(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    health_mgr: Any = Depends(get_deployment_health_manager),
) -> Dict[str, Any]:
    """Retrieve platform deployment configurations. Protected by platform.admin."""
    db_type = "sqlite"
    if health_mgr.db_manager and hasattr(health_mgr.db_manager, "engine"):
        if "postgresql" in str(health_mgr.db_manager.engine.url):
            db_type = "postgresql"

    return {
        "environment": os.getenv("JARVIS_SYSTEM_ENVIRONMENT", "production"),
        "replicas": 1,
        "storage_driver": db_type,
    }
