"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M9 API Routes)

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M9 API Routes)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.dependencies import get_kernel, require_permissions
from api.dto import ErrorDetail, ErrorEnvelope, MetaBlock
from core.exceptions import JarvisSkillError
from core.kernel import Kernel
from core.skills.installer import SkillInstaller
from core.skills.registry import SkillRegistry

router = APIRouter(tags=["skills"])

_require_install = require_permissions(["skill.install"])
_require_remove = require_permissions(["skill.remove"])
_require_read = require_permissions(["skill.read"])


def _success_response(
    data: object, meta: MetaBlock, status_code: int = 200
) -> JSONResponse:
    """Build a success envelope response dict without using the generic SuccessEnvelope.

    The generic SuccessEnvelope[T] breaks model_dump() on Python 3.14 + Pydantic v2
    (MockValSer serializer). This helper constructs the envelope dict manually.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "meta": meta.model_dump(mode="json"),
        },
    )


def _get_installer(kernel: Kernel = Depends(get_kernel)) -> SkillInstaller:
    """Resolve SkillInstaller from the Kernel DI container."""
    return kernel.container.resolve(SkillInstaller)


def _get_registry(kernel: Kernel = Depends(get_kernel)) -> SkillRegistry:
    """Resolve SkillRegistry from the Kernel DI container."""
    return kernel.container.resolve(SkillRegistry)


# ---------------------------------------------------------------------------
# POST /skills/install
# ---------------------------------------------------------------------------


@router.post("/install")
async def install_skill(
    request: Request,
    skill_name: str,
    source_url: str | None = None,
    version: str | None = None,
    force: bool = False,
    installer: SkillInstaller = Depends(_get_installer),
    _auth: object = Depends(_require_install),
) -> Response:
    """POST /api/v1/skills/install — Install a skill package.

    Delegates entirely to SkillInstaller.install(). No business logic here.
    """
    from core.skills.download_dto import DownloadedPackage

    # Build manifest payload from installer (simplified for Phase 18)
    # In production, this would fetch from source_url or local path
    manifest_payload = {
        "id": skill_name,
        "name": skill_name,
        "version": version or "1.0.0",
        "author": "user",
        "description": f"Skill package: {skill_name}",
        "entrypoint": "main.py",
        "permissions": ["file_read"],
        "dependencies": [],
        "signature": "a" * 64,
        "checksum": "b" * 64,
        "jarvis_api_version": "0.8",
        "min_runtime_version": "0.8",
        "approval_level": "L0",
        "trust_level": "COMMUNITY",
        "capabilities": [{"key": f"{skill_name}.skill.execute"}],
        "compatibility": {
            "platforms": ["windows", "linux"],
            "architectures": ["x64"],
            "python": ">=3.11",
            "jarvis_runtime": ">=0.8",
        },
        "limits": {
            "memory": "512MB",
            "cpu": "1",
            "timeout": 60,
            "network": False,
            "filesystem": "sandbox",
        },
        "isolation": "container",
    }

    downloaded = DownloadedPackage(
        skill_id=skill_name,
        version=version or "1.0.0",
        source_kind="local_package",
        package_path=f"skills/{skill_name}.zip",
        checksum="b" * 64,
        size_bytes=1024,
    )

    caller_id = str(getattr(request.state, "user_id", "anonymous"))

    try:
        result = await installer.install(
            manifest_payload=manifest_payload,
            downloaded=downloaded,
            caller_id=caller_id,
            force=force,
        )
    except JarvisSkillError as exc:
        error = ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(
            status_code=400,
            content=ErrorEnvelope(error=error).model_dump(mode="json"),
        )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    result_data = {
        "skill_id": result.skill_id,
        "name": result.name,
        "version": result.version,
        "state": result.state,
        "installed_at": result.installed_at,
        "success": result.success,
        "message": result.message,
        "rollback_available": result.rollback_available,
        "registry_state": result.registry_state,
    }

    return JSONResponse(
        status_code=201 if result.success else 400,
        content={
            "success": True,
            "data": result_data,
            "meta": meta.model_dump(mode="json"),
        },
    )


# ---------------------------------------------------------------------------
# POST /skills/remove
# ---------------------------------------------------------------------------


@router.post("/remove")
async def remove_skill(
    request: Request,
    skill_name: str,
    installer: SkillInstaller = Depends(_get_installer),
    _auth: object = Depends(_require_remove),
) -> Response:
    """POST /api/v1/skills/remove — Uninstall a skill."""
    try:
        removed = await installer.remove(skill_name)
    except JarvisSkillError as exc:
        error = ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(
            status_code=400,
            content=ErrorEnvelope(error=error).model_dump(mode="json"),
        )

    if not removed:
        error = ErrorDetail(
            code="SKILL_I006", message=f"Skill '{skill_name}' not found."
        )
        return JSONResponse(
            status_code=404,
            content=ErrorEnvelope(error=error).model_dump(mode="json"),
        )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    return _success_response(
        data={"removed": True, "skill_name": skill_name},
        meta=meta,
    )


# ---------------------------------------------------------------------------
# GET /skills
# ---------------------------------------------------------------------------


@router.get("/")
async def list_skills(
    request: Request,
    registry: SkillRegistry = Depends(_get_registry),
    _auth: object = Depends(_require_read),
) -> Response:
    """GET /api/v1/skills — List installed skills."""
    skills = registry.list_skills(active_only=True)

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    return _success_response(
        data={"skills": [s.model_dump() for s in skills], "total": len(skills)},
        meta=meta,
    )


# ---------------------------------------------------------------------------
# GET /skills/search
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_skills(
    request: Request,
    q: str = "",
    registry: SkillRegistry = Depends(_get_registry),
    _auth: object = Depends(_require_read),
) -> Response:
    """GET /api/v1/skills/search — Search skills by capability."""
    if q:
        results = registry.find_by_capability(q)
    else:
        results = registry.list_skills()

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    return _success_response(
        data={
            "results": [s.model_dump() for s in results],
            "total": len(results),
        },
        meta=meta,
    )


# ---------------------------------------------------------------------------
# GET /skills/{skill_id}
# ---------------------------------------------------------------------------


@router.get("/{skill_id}")
async def get_skill(
    request: Request,
    skill_id: str,
    registry: SkillRegistry = Depends(_get_registry),
    _auth: object = Depends(_require_read),
) -> Response:
    """GET /api/v1/skills/{skill_id} — Get skill metadata."""
    skill = registry.get_by_id(skill_id)
    if not skill:
        error = ErrorDetail(code="SKILL_I007", message=f"Skill '{skill_id}' not found.")
        return JSONResponse(
            status_code=404,
            content=ErrorEnvelope(error=error).model_dump(mode="json"),
        )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    return _success_response(data=skill.model_dump(), meta=meta)
