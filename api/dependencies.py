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

Module role: FastAPI dependency bridge. Every route handler obtains its
core service via these `Depends(...)` providers, which resolve from the
Kernel DI container (Frozen Constraint C4). This module NEVER instantiates
core classes; it only resolves already-registered singletons. Resolution
is fail-fast: if the Kernel is not booted or a singleton is missing, the
container raises JarvisSystemError (SYSTEM_001), which middleware maps to
an ErrorEnvelope (503). Dependency direction is api -> core only (C5).
"""

from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dto import AgentRunStatusResponse
from core.config import Settings
from core.health import HealthMonitor
from core.interfaces import EventBusInterface
from core.kernel import Kernel
from core.memory.database import db_manager
from core.reasoning.engine import ReasoningExecutionEngine
from core.tools.repository import WorkflowRepository
from core.tools.runtime import ToolRuntime
from core.tools.validator import WorkflowValidator
from core.tools.workflow_orchestrator import WorkflowOrchestrator

# Module-level Kernel handle, set once by api/main.py lifespan at boot.
# Kept Optional so import-time static analysis never sees a bare None deref.
_kernel: Optional[Kernel] = None


def set_kernel(kernel: Kernel) -> None:
    """Bind the booted Kernel instance. Called once by api/main.py lifespan.

    Args:
        kernel: A Kernel whose boot() has completed (container populated).

    Raises:
        RuntimeError: If called more than once (defensive; boot is idempotent
            at the Kernel level but this guard prevents accidental rebind).
    """
    global _kernel
    if _kernel is not None and _kernel is not kernel:
        raise RuntimeError("api.dependencies.set_kernel called twice")
    _kernel = kernel


def _require_kernel() -> Kernel:
    """Return the bound Kernel or fail fast if boot has not run.

    Returns:
        The bound Kernel instance.

    Raises:
        JarvisSystemError: code SYSTEM_001 if no Kernel is bound (Kernel
            not booted). Mapped by middleware to a 503 ErrorEnvelope.
    """
    if _kernel is None:
        # Imported lazily to avoid a circular import at module load.
        from core.exceptions import JarvisSystemError

        raise JarvisSystemError(
            code="SYSTEM_001",
            message="Kernel is not booted; cannot resolve API dependencies.",
        )
    return _kernel


def get_kernel() -> Kernel:
    """FastAPI dependency: return the bound Kernel singleton."""
    return _require_kernel()


def get_settings(kernel: Kernel = Depends(get_kernel)) -> Settings:
    """FastAPI dependency: resolve the frozen Settings singleton."""
    return kernel.container.resolve(Settings)


def get_event_bus(kernel: Kernel = Depends(get_kernel)) -> EventBusInterface:
    """FastAPI dependency: resolve the EventBusInterface singleton.

    Abstract-interface resolution requires the type-abstract ignore mirroring
    the existing pattern in core/kernel.py.
    """
    return kernel.container.resolve(EventBusInterface)  # type: ignore[type-abstract]


def get_health_monitor(kernel: Kernel = Depends(get_kernel)) -> HealthMonitor:
    """FastAPI dependency: resolve the HealthMonitor singleton (CR-002)."""
    return kernel.container.resolve(HealthMonitor)


def get_tool_runtime(kernel: Kernel = Depends(get_kernel)) -> ToolRuntime:
    """FastAPI dependency: resolve the ToolRuntime singleton."""
    return kernel.container.resolve(ToolRuntime)


def get_reasoning_engine(
    kernel: Kernel = Depends(get_kernel),
) -> ReasoningExecutionEngine:
    """FastAPI dependency: resolve the ReasoningExecutionEngine singleton."""
    return kernel.container.resolve(ReasoningExecutionEngine)


def get_workflow_validator(
    kernel: Kernel = Depends(get_kernel),
) -> WorkflowValidator:
    """FastAPI dependency: resolve the WorkflowValidator singleton (Phase 13)."""
    return kernel.container.resolve(WorkflowValidator)


def get_workflow_repository(
    kernel: Kernel = Depends(get_kernel),
) -> WorkflowRepository:
    """FastAPI dependency: resolve the WorkflowRepository singleton (Phase 13)."""
    return kernel.container.resolve(WorkflowRepository)


def get_workflow_orchestrator(
    kernel: Kernel = Depends(get_kernel),
) -> WorkflowOrchestrator:
    """FastAPI dependency: resolve the WorkflowOrchestrator singleton (Phase 13)."""
    return kernel.container.resolve(WorkflowOrchestrator)


# In-memory storage of accepted runs for Phase 14
_agent_runs: dict[UUID, AgentRunStatusResponse] = {}


def get_agent_runs() -> dict[UUID, AgentRunStatusResponse]:
    """FastAPI dependency: retrieve the in-memory agent run status registry."""
    return _agent_runs


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield transactional database sessions."""
    async with db_manager.session() as session:
        yield session
