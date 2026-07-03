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

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from api import stream_service
from api.dependencies import set_kernel
from api.middleware import RequestStateMiddleware, register_exception_handlers
from api.middleware.auth_middleware import AuthenticationMiddleware
from api.middleware.rate_limit_middleware import RateLimitMiddleware
from api.routes import agent, auth, health, skills, users, workflow
from core.kernel import Kernel

logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages the startup and shutdown sequence of the global Kernel container."""
    kernel = Kernel()
    await kernel.initialize()

    config_path = os.getenv("JARVIS_CONFIG_PATH", "config.yaml")
    boot_ok = await kernel.boot(config_path)
    if not boot_ok:
        raise RuntimeError("Kernel boot failed during API gateway startup.")

    set_kernel(kernel)

    # Trigger resume manager startup recovery (Phase 15)
    try:
        from core.tools.resume_manager import ResumeManager

        resume_manager = kernel.container.resolve(ResumeManager)
        await resume_manager.resume_all()
    except Exception as e:
        logger.warning("Startup recovery failed: %s", str(e))

    yield

    await kernel.lifecycle_manager.stop_all()
    await kernel.lifecycle_manager.shutdown_all()
    await kernel.shutdown()


def create_app() -> FastAPI:
    """FastAPI application factory configuring gateway components."""
    app = FastAPI(
        title="JARVIS OS Gateway",
        description="FastAPI gateway exposing core execution engine and workflow features",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 1. Register global RequestStateMiddleware for request latency tracing
    app.add_middleware(RequestStateMiddleware)

    # 2. Register AuthenticationMiddleware (runs after rate limiting)
    app.add_middleware(AuthenticationMiddleware)

    # 3. Register RateLimitMiddleware (runs first, before authentication)
    app.add_middleware(RateLimitMiddleware)

    # 4. Register exception handler mappings
    register_exception_handlers(app)

    # 4. Mount HTTP endpoints under /api/v1
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(workflow.router, prefix="/api/v1")
    app.include_router(skills.router, prefix="/api/v1")

    # 5. Mount WebSocket telemetry endpoint under /ws/v1
    app.include_router(stream_service.router, prefix="/ws/v1")

    return app


app = create_app()
