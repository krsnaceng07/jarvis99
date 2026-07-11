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

from typing import Any, AsyncGenerator, Awaitable, Callable, List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dto import AgentRunStatusResponse
from core.config import Settings
from core.exceptions import AuthenticationError
from core.health import HealthMonitor
from core.interfaces import EventBusInterface
from core.kernel import Kernel
from core.memory.database import db_manager
from core.reasoning.engine import ReasoningExecutionEngine
from core.security.auth_context import RequestContext, active_context
from core.security.auth_service import AuthenticationService
from core.security.rbac_service import RbacService
from core.tools.execution_repository import ExecutionRepository
from core.tools.repository import WorkflowRepository
from core.tools.runtime import ToolRuntime
from core.tools.security_repository import SecurityRepository
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


def get_execution_repository(
    kernel: Kernel = Depends(get_kernel),
) -> ExecutionRepository:
    """FastAPI dependency: resolve the ExecutionRepository singleton (Phase 15)."""
    return kernel.container.resolve(ExecutionRepository)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield transactional database sessions."""
    async with db_manager.session() as session:
        yield session


def get_security_repository(
    kernel: Kernel = Depends(get_kernel),
) -> SecurityRepository:
    """FastAPI dependency: resolve the SecurityRepository singleton."""
    return kernel.container.resolve(SecurityRepository)


def get_vault_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the VaultManager singleton."""
    from core.security.vault import VaultManager

    return kernel.container.resolve(VaultManager)


def get_authentication_service(
    kernel: Kernel = Depends(get_kernel),
) -> AuthenticationService:
    """FastAPI dependency: resolve the AuthenticationService singleton."""
    return kernel.container.resolve(AuthenticationService)


def get_rbac_service(
    kernel: Kernel = Depends(get_kernel),
) -> RbacService:
    """FastAPI dependency: resolve the RbacService singleton."""
    return kernel.container.resolve(RbacService)


def get_sync_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the SyncManager singleton."""
    from core.security.sync import SyncManager

    return kernel.container.resolve(SyncManager)


def get_federation_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the FederationManager singleton."""
    from core.runtime.federation import FederationManager

    return kernel.container.resolve(FederationManager)


def get_admin_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the AdminManager singleton."""
    from core.runtime.admin import AdminManager

    return kernel.container.resolve(AdminManager)


def require_permissions(
    required_permissions: List[str],
) -> Callable[..., Awaitable[RequestContext]]:
    """FastAPI dependency builder enforcing active user context permission scopes."""

    async def dependency() -> RequestContext:
        ctx = active_context.get()
        if not ctx:
            raise AuthenticationError(
                code="AUTH_005", message="Authentication credentials were not provided."
            )

        user_permissions = set(ctx.permissions)
        if not all(scope in user_permissions for scope in required_permissions):
            raise AuthenticationError(
                code="AUTH_006",
                message="Insufficient permissions to access this resource.",
            )
        return ctx

    return dependency


def get_deployment_health_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the DeploymentHealthManager singleton."""
    from core.runtime.deployment import DeploymentHealthManager

    return kernel.container.resolve(DeploymentHealthManager)


def get_mission_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the MissionManager singleton."""
    from core.runtime.mission import MissionManager

    return kernel.container.resolve(MissionManager)


def get_scale_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the ScaleManager singleton."""
    from core.runtime.scale import ScaleManager

    return kernel.container.resolve(ScaleManager)


def get_consensus_manager(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the ConsensusManager singleton."""
    from core.runtime.consensus import ConsensusManager

    return kernel.container.resolve(ConsensusManager)


def get_brain_kernel(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the BrainKernel singleton."""
    from core.runtime.brain_kernel import BrainKernel

    return kernel.container.resolve(BrainKernel)


def get_neural_layer(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the NeuralLayer singleton."""
    from core.runtime.neural.neural_layer import NeuralLayer

    return kernel.container.resolve(NeuralLayer)


def get_decision_engine(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the DecisionEngine singleton."""
    from core.runtime.policy.decision_engine import DecisionEngine

    return kernel.container.resolve(DecisionEngine)


def get_reflection_engine(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the ReflectionEngine singleton."""
    from core.runtime.neural.reflection_engine import ReflectionEngine

    return kernel.container.resolve(ReflectionEngine)


def get_learning_engine(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the LearningEngine singleton."""
    from core.runtime.neural.learning_engine import LearningEngine

    return kernel.container.resolve(LearningEngine)


def get_memory_orchestrator(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the MemoryOrchestrator singleton (Phase 19 M7)."""
    from core.memory.orchestrator import MemoryOrchestrator

    return kernel.container.resolve(MemoryOrchestrator)


def get_context_assembler(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the ContextAssembly singleton."""
    from core.memory.context_assembly import ContextAssembly

    return kernel.container.resolve(ContextAssembly)


def get_memory_coordinator(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the MemoryCoordinator singleton."""
    from core.memory.memory_coordinator import MemoryCoordinator

    return kernel.container.resolve(MemoryCoordinator)


def get_workflow_engine(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the WorkflowEngine singleton."""
    from core.workflow.workflow_engine import WorkflowEngine

    return kernel.container.resolve(WorkflowEngine)


def get_identity_service(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the IdentityService singleton."""
    from core.reasoning.identity import IdentityService

    return kernel.container.resolve(IdentityService)


def get_identity_repository(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the IdentityRepository singleton."""
    from core.reasoning.identity_repository import IdentityRepository

    return kernel.container.resolve(IdentityRepository)


def get_goal_service(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the GoalService singleton (Phase 43)."""
    from core.reasoning.goal import GoalService

    return kernel.container.resolve(GoalService)


def get_goal_repository(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the GoalRepository singleton (Phase 43)."""
    from core.reasoning.goal_repository import GoalRepository

    return kernel.container.resolve(GoalRepository)


def get_goal_scheduler(
    kernel: Kernel = Depends(get_kernel),
) -> Any:
    """FastAPI dependency: resolve the GoalScheduler singleton (Phase 44)."""
    from core.mission.mission_scheduler import GoalScheduler

    return kernel.container.resolve(GoalScheduler)


# ---------------------------------------------------------------------------
# Phase 45 M6.4.A — DistributedRouter + WorkerRegistry providers
#
# Pattern: constructed per-request (cheap, no inter-request state).
# WorkerRegistry wraps the shared db_manager; DistributedRouter wraps
# the registry. Both are stateless across calls.
# ---------------------------------------------------------------------------


def get_worker_registry() -> Any:
    """FastAPI dependency: build a WorkerRegistry bound to the shared db."""
    from core.mission.worker_registry import WorkerRegistry

    return WorkerRegistry(db_manager=db_manager)


def get_distributed_router(
    registry: Any = Depends(get_worker_registry),
) -> Any:
    """FastAPI dependency: build a DistributedRouter bound to the registry."""
    from core.mission.distributed_router import DistributedRouter

    return DistributedRouter(worker_registry=registry)
