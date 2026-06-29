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

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from api import stream_service
from api.dependencies import set_kernel
from api.middleware import RequestStateMiddleware, register_exception_handlers
from api.routes import agent, health, workflow
from core.kernel import Kernel


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages the startup and shutdown sequence of the global Kernel container."""
    # Startup: Instantiate, initialize, and start the Core Kernel container
    kernel = Kernel()
    await kernel.initialize()
    await kernel.start()
    set_kernel(kernel)

    yield

    # Shutdown: Gracefully stop and shutdown the Kernel container
    await kernel.stop()
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

    # 2. Register exception handler mappings
    register_exception_handlers(app)

    # 3. Mount HTTP endpoints under /api/v1
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(workflow.router, prefix="/api/v1")

    # 4. Mount WebSocket telemetry endpoint under /ws/v1
    app.include_router(stream_service.router, prefix="/ws/v1")

    return app


app = create_app()
