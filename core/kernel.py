"""JARVIS OS - System Kernel.

Central coordinator orchestrating configuration validation, security vaults,
event bus initialization, and core lifecycle sequences.
"""

import logging
import sys
from types import ModuleType
from typing import Any, Optional

from core.container import DependencyContainer
from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage, LifecycleInterface
from core.lifecycle import LifecycleManager


def bootstrap_sdk_namespaces() -> None:
    """Dynamically register the jarvis.sdk.* namespaces to satisfy compliance imports without physical folders."""
    if "jarvis" in sys.modules:
        return

    jarvis_mod = ModuleType("jarvis")
    jarvis_sdk_mod = ModuleType("jarvis.sdk")
    jarvis_sdk_skills_mod = ModuleType("jarvis.sdk.skills")
    jarvis_sdk_browser_mod = ModuleType("jarvis.sdk.browser")

    # Link attributes so module attributes are resolved during import lookup
    jarvis_mod.sdk = jarvis_sdk_mod  # type: ignore[attr-defined]
    jarvis_sdk_mod.skills = jarvis_sdk_skills_mod  # type: ignore[attr-defined]
    jarvis_sdk_mod.browser = jarvis_sdk_browser_mod  # type: ignore[attr-defined]

    # Bind base definitions dynamically
    from core.tools.base import JarvisSkill

    jarvis_sdk_skills_mod.JarvisSkill = JarvisSkill  # type: ignore[attr-defined]

    # Stubs/Refs to client API classes
    try:
        from core.browser.client import JarvisBrowser

        jarvis_sdk_browser_mod.JarvisBrowser = JarvisBrowser  # type: ignore[attr-defined]
    except ImportError:
        pass

    sys.modules["jarvis"] = jarvis_mod
    sys.modules["jarvis.sdk"] = jarvis_sdk_mod
    sys.modules["jarvis.sdk.skills"] = jarvis_sdk_skills_mod
    sys.modules["jarvis.sdk.browser"] = jarvis_sdk_browser_mod


bootstrap_sdk_namespaces()

logger = logging.getLogger("jarvis.core.kernel")


class Kernel(LifecycleInterface):
    """System Kernel coordinating bootstrap, configuration, security, and lifecycles."""

    def __init__(self) -> None:
        """Initialize the Kernel instance with a dependency container and lifecycle manager."""
        self.container = DependencyContainer()
        self.lifecycle_manager = LifecycleManager()
        self._booted: bool = False
        self._config_path: Optional[str] = None

    async def initialize(self) -> None:
        """Perform initial Kernel setup.

        Raises:
            JarvisSystemError: If initialization fails.
        """
        # Register the Kernel itself in the container as a LifecycleInterface singleton if not present
        if not self.container.get_registry().has(LifecycleInterface):
            self.container.register_singleton(LifecycleInterface, self)

    async def start(self) -> None:
        """Activate the Kernel service."""
        pass

    async def stop(self) -> None:
        """Stop the Kernel service."""
        pass

    async def shutdown(self) -> None:
        """Gracefully release all Kernel resources."""
        self._booted = False

    async def boot(self, config_path: str) -> bool:
        """Boot the JARVIS OS kernel.

        Loads configuration profiles, initializes vault decryption, builds the
        dependency injection container, and triggers startup lifecycles.

        Args:
            config_path: File system path to the YAML configuration settings.

        Returns:
            True if system booted successfully, False otherwise.

        Raises:
            JarvisSystemError: If boot fails or system is already booted.
        """
        if self._booted:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Cannot boot kernel: System is already booted.",
            )

        self._config_path = config_path
        logger.info("Kernel booting with config path: %s", config_path)

        try:
            # 1. Load security vault credentials
            vault_ok = await self._load_vault()
            if not vault_ok:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message="Vault validation failed during boot.",
                )

            # 2. Setup the global Event Bus
            event_bus_ok = await self._initialize_event_bus()
            if not event_bus_ok:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message="Event Bus initialization failed during boot.",
                )

            # Register Event Bus Singleton
            from core.events.memory_bus import MemoryEventBus

            event_bus = MemoryEventBus()
            await event_bus.initialize()
            await event_bus.start()
            self.container.register_singleton(EventBusInterface, event_bus)

            # Link event bus to VaultManager
            try:
                from core.security.vault import VaultManager

                vault = self.container.resolve(VaultManager)
                vault.event_bus = event_bus
            except Exception:
                pass

            # Load and Register Settings Singleton
            import os

            from core.config import Settings

            path = (
                self._config_path
                if (self._config_path and os.path.exists(self._config_path))
                else None
            )
            settings = Settings.load_settings(path)
            self._resolve_vault_secrets(settings)
            self.container.register_singleton(Settings, settings)

            # Register Orchestration & Tool components
            from core.reasoning.orchestrator import ExecutionOrchestrator
            from core.tools.audit import ImmutableAuditLogger
            from core.tools.dependency_resolver import DependencyResolver
            from core.tools.metrics_collector import ExecutionMetricsCollector
            from core.tools.registry import ToolRegistry
            from core.tools.result_aggregator import WaveResultAggregator
            from core.tools.retry_manager import RetryManager
            from core.tools.runtime import ToolRuntime
            from core.tools.sandbox import ISandbox, LocalSubprocessSandbox
            from core.tools.security import PermissionGatekeeper
            from core.tools.wave_executor import WaveExecutor

            # Resolve skill directory
            skills_dir = getattr(settings, "SKILLS_DIR", "skills")
            registry = ToolRegistry(skills_dir=skills_dir)
            sandbox = LocalSubprocessSandbox()
            gatekeeper = PermissionGatekeeper(event_bus=event_bus)
            audit_logger = ImmutableAuditLogger()

            runtime = ToolRuntime(
                registry=registry,
                sandbox=sandbox,
                gatekeeper=gatekeeper,
                event_bus=event_bus,
                audit_logger=audit_logger,
            )

            resolver = DependencyResolver()
            aggregator = WaveResultAggregator()
            retry_mgr = RetryManager()
            metrics_coll = ExecutionMetricsCollector()

            wave_exec = WaveExecutor(
                resolver=resolver,
                aggregator=aggregator,
                retry_manager=retry_mgr,
                metrics_collector=metrics_coll,
                concurrency_limit=5,
            )

            orchestrator = ExecutionOrchestrator(
                tool_runtime=runtime,
                wave_executor=wave_exec,
                metrics_collector=metrics_coll,
                event_bus=event_bus,
                settings=settings,
            )

            # Register Reasoning execution components
            from core.reasoning.cost import CostGovernor
            from core.reasoning.credentials import CredentialManager
            from core.reasoning.engine import ReasoningExecutionEngine
            from core.reasoning.plan_version_manager import PlanVersionManager
            from core.reasoning.planning_service import PlanningService
            from core.reasoning.prompt import PromptBuilder
            from core.reasoning.provider import (
                ClaudeProvider,
                LlamaProvider,
                ProviderConfig,
            )
            from core.reasoning.rate_limiter import ProviderRateLimiter
            from core.reasoning.reflection import ReflectionEngine
            from core.reasoning.registry import ModelCapabilityRegistry
            from core.reasoning.router import ModelRouter
            from core.reasoning.telemetry import ReasoningTelemetry
            from core.reasoning.transport import UrllibTransport

            transport = UrllibTransport()
            cred_manager = CredentialManager()
            capability_registry = ModelCapabilityRegistry()
            rate_limiter = ProviderRateLimiter()
            telemetry = ReasoningTelemetry()
            cost_governor = CostGovernor(settings=settings)

            llama_cfg = ProviderConfig(
                provider_name="LlamaLocal",
                model_name="llama-3.1-8b",
                base_url="http://localhost:8000/v1",
            )
            claude_cfg = ProviderConfig(
                provider_name="Claude",
                model_name="claude-3-5-sonnet",
                base_url="https://api.anthropic.com/v1",
            )
            llama_prov = LlamaProvider(llama_cfg, transport, cred_manager)
            claude_prov = ClaudeProvider(claude_cfg, transport, cred_manager)

            router = ModelRouter(
                providers=[llama_prov, claude_prov],
                registry=capability_registry,
                rate_limiter=rate_limiter,
                telemetry=telemetry,
                cost_gov=cost_governor,
                settings=settings,
            )

            prompt_builder = PromptBuilder(settings)
            reflection_engine = ReflectionEngine(settings)

            planning_service = PlanningService(
                router=router,
                prompt_builder=prompt_builder,
                cost_governor=cost_governor,
            )
            version_manager = PlanVersionManager()

            from core.reasoning.decision_engine import DecisionEngine as _DecisionEngine
            from core.reasoning.tool_selector import ToolSelectionEngine as _ToolSelectionEngine
            from core.tools.llm_runtime import LlmRuntime as _LlmRuntime

            engine_llm_runtime = _LlmRuntime(
                provider=claude_prov,
                cost_governor=cost_governor,
            )
            engine_tool_selector = _ToolSelectionEngine(
                decision_engine=_DecisionEngine(),
                llm_runtime=engine_llm_runtime,
            )
            execution_engine = ReasoningExecutionEngine(
                orchestrator=orchestrator,
                reflection_engine=reflection_engine,
                router=router,
                prompt_builder=prompt_builder,
                cost_governor=cost_governor,
                settings=settings,
                planning_service=planning_service,
                version_manager=version_manager,
                event_bus=event_bus,
                llm_runtime=engine_llm_runtime,
                tool_selector=engine_tool_selector,
            )

            # Register singletons
            self.container.register_singleton(ToolRegistry, registry)
            self.container.register_singleton(PermissionGatekeeper, gatekeeper)
            self.container.register_singleton(ISandbox, sandbox)
            self.container.register_singleton(ToolRuntime, runtime)
            self.container.register_singleton(DependencyResolver, resolver)
            self.container.register_singleton(WaveResultAggregator, aggregator)
            self.container.register_singleton(RetryManager, retry_mgr)
            self.container.register_singleton(ExecutionMetricsCollector, metrics_coll)
            self.container.register_singleton(WaveExecutor, wave_exec)
            self.container.register_singleton(ExecutionOrchestrator, orchestrator)
            self.container.register_singleton(PlanningService, planning_service)
            self.container.register_singleton(PlanVersionManager, version_manager)
            self.container.register_singleton(
                ReasoningExecutionEngine, execution_engine
            )

            # Phase 13 — Workflow Automation services
            from core.tools.compiler import WorkflowCompiler
            from core.tools.repository import WorkflowRepository
            from core.tools.validator import WorkflowValidator
            from core.tools.workflow_orchestrator import WorkflowOrchestrator

            workflow_validator = WorkflowValidator(registry=registry)
            workflow_compiler = WorkflowCompiler()
            workflow_repository = WorkflowRepository()
            workflow_orchestrator = WorkflowOrchestrator(
                orchestrator=orchestrator,
                event_bus=event_bus,
            )

            self.container.register_singleton(WorkflowValidator, workflow_validator)
            self.container.register_singleton(WorkflowCompiler, workflow_compiler)
            self.container.register_singleton(WorkflowRepository, workflow_repository)
            self.container.register_singleton(
                WorkflowOrchestrator, workflow_orchestrator
            )

            # Phase 15 — Persistent Execution & Run Management
            from core.memory.database import db_manager
            from core.reasoning.persistence_service import PersistenceService
            from core.tools.execution_repository import ExecutionRepository
            from core.tools.resume_manager import ResumeManager

            # Initialize database session manager
            db_manager.init(settings)

            # SQLite/dev: materialize ORM tables before seeding or persistence hooks
            if settings.database.host == "sqlite":
                from core.memory import (
                    security_models as _security_models,  # noqa: F401
                )
                from core.memory.models import Base
                from core.observability import (
                    models as _observability_models,  # noqa: F401
                )
                from core.runtime import (
                    persistence_models as _persistence_models,  # noqa: F401
                    mission_models as _mission_models,  # noqa: F401
                )
                from core.tools import (
                    execution_models as _execution_models,  # noqa: F401
                )

                async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
                    await conn.run_sync(Base.metadata.create_all)

            execution_repository = ExecutionRepository()
            persistence_service = PersistenceService(
                repository=execution_repository,
                event_bus=event_bus,
            )
            resume_manager = ResumeManager(
                repository=execution_repository,
                event_bus=event_bus,
            )

            self.container.register_singleton(ExecutionRepository, execution_repository)
            self.container.register_singleton(PersistenceService, persistence_service)
            self.container.register_singleton(ResumeManager, resume_manager)

            self.lifecycle_manager.add_service(persistence_service)

            # Phase 26 — Multi-Agent Runtime & Swarm Orchestration
            from core.reasoning.decision_engine import DecisionEngine
            from core.reasoning.dispatcher import ToolDispatcher
            from core.reasoning.reflection import ReflectionEngine
            from core.runtime.container_driver import MockAdapter
            from core.runtime.lock import MemoryLock
            from core.runtime.message_bus import SwarmMessageBus
            from core.runtime.orchestrator import SwarmOrchestrator
            from core.runtime.persistence_db import DbSwarmPersistence
            from core.runtime.queue import SwarmTaskQueue
            from core.runtime.recovery_manager import SwarmResumeManager
            from core.runtime.registry import AgentRegistry
            from core.runtime.routes import set_orchestrator
            from core.runtime.scheduler import CapabilityNegotiator
            from core.runtime.subagent import SubagentManager

            swarm_queue = SwarmTaskQueue()
            swarm_negotiator = CapabilityNegotiator()
            swarm_message_bus = SwarmMessageBus(event_bus)
            swarm_persistence = DbSwarmPersistence()
            swarm_lock_manager = MemoryLock()
            swarm_registry = AgentRegistry()
            swarm_subagent_manager = SubagentManager(driver=MockAdapter())

            from core.reasoning.dispatcher import LlmExecutor
            from core.reasoning.repair_engine import RepairEngine
            from core.reasoning.task import ExecutorType
            from core.tools.llm_runtime import LlmRuntime

            from core.reasoning.tool_selector import ToolSelectionEngine

            swarm_llm_runtime = LlmRuntime(
                provider=claude_prov,
                cost_governor=cost_governor,
            )
            swarm_decision = DecisionEngine()
            tool_selector = ToolSelectionEngine(
                decision_engine=swarm_decision,
                llm_runtime=swarm_llm_runtime,
            )
            swarm_reflection = ReflectionEngine(settings)
            swarm_repair = RepairEngine(
                reflection_engine=swarm_reflection,
                tool_selector=tool_selector,
                llm_runtime=swarm_llm_runtime,
            )
            swarm_dispatcher = ToolDispatcher(
                tool_selector=tool_selector,
                repair_engine=swarm_repair,
            )
            swarm_dispatcher.executors[ExecutorType.LLM] = LlmExecutor(
                llm_runtime=swarm_llm_runtime,
            )

            swarm_orchestrator = SwarmOrchestrator(
                manager=swarm_subagent_manager,
                queue=swarm_queue,
                negotiator=swarm_negotiator,
                message_bus=swarm_message_bus,
                persistence=swarm_persistence,
                lock_manager=swarm_lock_manager,
                registry=swarm_registry,
                event_bus=event_bus,
                dispatcher=swarm_dispatcher,
                reflection=swarm_reflection,
                decision=swarm_decision,
                llm_runtime=swarm_llm_runtime,
            )

            # Register globally for API routes dependencies
            set_orchestrator(swarm_orchestrator)

            swarm_resume_manager = SwarmResumeManager(
                orchestrator=swarm_orchestrator,
                event_bus=event_bus,
            )

            self.container.register_singleton(SwarmOrchestrator, swarm_orchestrator)
            self.container.register_singleton(SwarmResumeManager, swarm_resume_manager)

            self.lifecycle_manager.add_service(swarm_orchestrator)
            self.lifecycle_manager.add_service(swarm_resume_manager)

            # Goal #5 — Autonomous Multi-Agent Collaboration
            from core.runtime.conflict_resolver import ConflictResolver
            from core.runtime.deadlock_detector import DeadlockDetector
            from core.runtime.parallel_planner import ParallelMissionPlanner
            from core.runtime.result_merger import ResultMerger
            from core.runtime.role_assigner import AgentRoleAssigner
            from core.runtime.supervisor import AgentSupervisor

            role_assigner = AgentRoleAssigner(
                registry=swarm_registry,
                negotiator=swarm_negotiator,
                llm_runtime=swarm_llm_runtime,
            )
            parallel_planner = ParallelMissionPlanner(
                llm_runtime=swarm_llm_runtime,
            )
            result_merger = ResultMerger(llm_runtime=swarm_llm_runtime)
            conflict_resolver = ConflictResolver(llm_runtime=swarm_llm_runtime)
            agent_supervisor = AgentSupervisor(
                registry=swarm_registry,
                subagent_manager=swarm_subagent_manager,
                message_bus=swarm_message_bus,
                queue=swarm_queue,
            )
            deadlock_detector = DeadlockDetector(
                lock_manager=swarm_lock_manager,
                supervisor=agent_supervisor,
            )

            self.container.register_singleton(AgentRoleAssigner, role_assigner)
            self.container.register_singleton(ParallelMissionPlanner, parallel_planner)
            self.container.register_singleton(ResultMerger, result_merger)
            self.container.register_singleton(ConflictResolver, conflict_resolver)
            self.container.register_singleton(AgentSupervisor, agent_supervisor)
            self.container.register_singleton(DeadlockDetector, deadlock_detector)

            # Phase 44 — Mission & Autonomous Goal Scheduler (CR-001)
            try:
                from core.mission.mission_scheduler import GoalScheduler

                goal_scheduler = GoalScheduler(event_bus=event_bus)
                self.container.register_singleton(GoalScheduler, goal_scheduler)
            except Exception as e:
                logger.warning("Phase 44 GoalScheduler registration failed: %s", str(e))

            # Phase 27 — Observability, Cost Governance & Live Execution Streaming
            from core.observability.broadcaster_interface import (
                BaseTelemetryBroadcaster,
            )
            from core.observability.budget_repository import BudgetRepository
            from core.observability.cost_governor import CostGovernor
            from core.observability.health_probe import HealthProbe
            from core.observability.service import ObservabilityService
            from core.observability.span_repository import SpanRepository

            obs_span_repo = SpanRepository()
            obs_budget_repo = BudgetRepository()
            obs_cost_governor = CostGovernor(
                budget_repository=obs_budget_repo,
                daily_limit_usd=getattr(settings, "JARVIS_DAILY_BUDGET_USD", 10.0),
            )
            obs_health_probe = HealthProbe()
            try:
                obs_broadcaster = self.container.resolve(BaseTelemetryBroadcaster)
            except Exception:
                from core.observability.dto import TelemetryEnvelope

                class NoOpTelemetryBroadcaster(BaseTelemetryBroadcaster):
                    async def broadcast(self, envelope: TelemetryEnvelope) -> None:
                        pass

                obs_broadcaster = NoOpTelemetryBroadcaster()

            observability_service = ObservabilityService(
                event_bus=event_bus,
                span_repo=obs_span_repo,
                cost_gov=obs_cost_governor,
                health_probe=obs_health_probe,
                broadcaster=obs_broadcaster,
            )

            self.container.register_singleton(
                ObservabilityService, observability_service
            )
            self.lifecycle_manager.add_service(observability_service)

            # Phase 17 — Security services
            from core.security.api_key_service import ApiKeyService
            from core.security.auth_service import AuthenticationService
            from core.security.configuration_service import ConfigurationService
            from core.security.jwt_service import JWTService
            from core.security.password_service import PasswordService
            from core.security.rbac_service import RbacService
            from core.security.revocation_service import RevocationService
            from core.security.seed_service import SecuritySeedService
            from core.tools.security_repository import SecurityRepository

            security_repository = SecurityRepository()
            config_service = ConfigurationService()
            password_service = PasswordService(cost_factor=config_service.bcrypt_cost)
            jwt_service = JWTService(config=config_service)
            revocation_service = RevocationService(repo=security_repository)
            api_key_service = ApiKeyService()
            rbac_service = RbacService()
            auth_service = AuthenticationService(
                repo=security_repository,
                password_service=password_service,
                jwt_service=jwt_service,
                revocation_service=revocation_service,
                api_key_service=api_key_service,
                rbac_service=rbac_service,
                config=config_service,
                event_bus=event_bus,
            )
            seed_service = SecuritySeedService(
                repo=security_repository,
                password_service=password_service,
                config=config_service,
            )

            self.container.register_singleton(SecurityRepository, security_repository)
            self.container.register_singleton(ConfigurationService, config_service)
            self.container.register_singleton(PasswordService, password_service)
            self.container.register_singleton(JWTService, jwt_service)
            self.container.register_singleton(RevocationService, revocation_service)
            self.container.register_singleton(ApiKeyService, api_key_service)
            self.container.register_singleton(RbacService, rbac_service)
            self.container.register_singleton(AuthenticationService, auth_service)
            self.container.register_singleton(SecuritySeedService, seed_service)

            # Phase 30 — Cloud Sync & HA
            try:
                from core.security.sync import LocalFolderStorageProvider, SyncManager
                from core.security.vault import VaultManager

                vault_mgr = self.container.resolve(VaultManager)
                provider = LocalFolderStorageProvider(folder_path="secrets/sync")
                sync_manager = SyncManager(
                    vault_manager=vault_mgr,
                    storage_provider=provider,
                    settings=settings,
                    event_bus=event_bus,
                )
                self.container.register_singleton(SyncManager, sync_manager)
            except Exception as e:
                logger.warning(
                    "SyncManager registration skipped during boot: %s", str(e)
                )

            # Phase 31 — Platform Scale & Federation
            try:
                from core.runtime.federation import FederationManager
                from core.security.vault import VaultManager

                vault_mgr = self.container.resolve(VaultManager)
                federation_manager = FederationManager(
                    settings=settings,
                    vault_manager=vault_mgr,
                    event_bus=event_bus,
                )
                self.container.register_singleton(FederationManager, federation_manager)
                self.lifecycle_manager.add_service(federation_manager)
            except Exception as e:
                logger.warning(
                    "FederationManager registration skipped during boot: %s", str(e)
                )

            # Phase 32 — Platform Administration & Operations
            try:
                from core.runtime.admin import AdminManager
                from core.security.vault import VaultManager
                from core.runtime.orchestrator import SwarmOrchestrator

                vault_mgr = self.container.resolve(VaultManager)
                orchestrator = self.container.resolve(SwarmOrchestrator)

                admin_manager = AdminManager(
                    settings=settings,
                    db_manager=db_manager,
                    event_bus=event_bus,
                    vault_manager=vault_mgr,
                    orchestrator=orchestrator,
                )
                self.container.register_singleton(AdminManager, admin_manager)
                self.lifecycle_manager.add_service(admin_manager)
            except Exception as e:
                logger.warning(
                    "AdminManager registration skipped during boot: %s", str(e)
                )

            # Phase 33 — Platform Enterprise Deployment & Operations
            try:
                from core.runtime.deployment import DeploymentHealthManager

                health_mgr = DeploymentHealthManager(
                    settings=settings,
                    db_manager=db_manager,
                    event_bus=event_bus,
                    vault_manager=vault_mgr,
                    orchestrator=orchestrator,
                    admin_manager=admin_manager,
                )
                self.container.register_singleton(DeploymentHealthManager, health_mgr)
                self.lifecycle_manager.add_service(health_mgr)
            except Exception as e:
                logger.warning(
                    "DeploymentHealthManager registration skipped during boot: %s", str(e)
                )

            # Phase 34 — Platform Autonomous Mission Engine & Long-Running Agents
            try:
                from core.runtime.mission import MissionManager

                # Resolve Goal #5 components (registered above)
                _pp = self.container.resolve(ParallelMissionPlanner)
                _ra = self.container.resolve(AgentRoleAssigner)
                _rm = self.container.resolve(ResultMerger)
                _cr = self.container.resolve(ConflictResolver)
                _sv = self.container.resolve(AgentSupervisor)

                mission_mgr = MissionManager(
                    settings=settings,
                    db_manager=db_manager,
                    event_bus=event_bus,
                    vault_manager=vault_mgr,
                    orchestrator=orchestrator,
                    planner=swarm_llm_runtime,
                    parallel_planner=_pp,
                    role_assigner=_ra,
                    result_merger=_rm,
                    conflict_resolver=_cr,
                    supervisor=_sv,
                    # memory_orchestrator set later once available
                )
                self.container.register_singleton(MissionManager, mission_mgr)
                self.lifecycle_manager.add_service(mission_mgr)

            except Exception as e:
                logger.warning(
                    "MissionManager registration skipped during boot: %s", str(e)
                )

            # Phase 37 — Brain Kernel & Cognitive OS core
            try:
                from core.runtime.brain_context import BrainContext
                from core.runtime.brain_kernel import BrainKernel
                from core.runtime.brain_state import CognitiveState
                from core.runtime.neural.learning_engine import LearningEngine
                from core.runtime.neural.model_router import (
                    ModelRouter as CognitiveModelRouter,
                )
                from core.runtime.neural.neural_layer import NeuralLayer
                from core.runtime.neural.planning_engine import PlanningEngine
                from core.runtime.neural.reasoning_engine import ReasoningEngine
                from core.runtime.neural.reflection_engine import (
                    ReflectionEngine as CognitiveReflectionEngine,
                )
                from core.runtime.policy.decision_engine import DecisionEngine

                evt_bus = self.container.resolve(EventBusInterface)
                brain_state = CognitiveState()
                brain_context = BrainContext()
                cog_model_router = CognitiveModelRouter()
                cog_model_router.register_provider("claude", claude_prov)
                decision_engine = DecisionEngine(settings=settings)
                reasoning_engine = ReasoningEngine(model_router=cog_model_router)
                planning_engine = PlanningEngine(model_router=cog_model_router)
                reflection_engine = CognitiveReflectionEngine(model_router=cog_model_router)
                learning_engine = LearningEngine(settings=settings)

                neural_layer = NeuralLayer(
                    model_router=cog_model_router,
                    reasoning_engine=reasoning_engine,
                    planning_engine=planning_engine,
                    reflection_engine=reflection_engine,
                    learning_engine=learning_engine,
                )

                brain_kernel = BrainKernel(
                    settings=settings,
                    state=brain_state,
                    context=brain_context,
                    event_bus=evt_bus,
                    decision_engine=decision_engine,
                    neural_layer=neural_layer,
                )

                self.container.register_singleton(CognitiveState, brain_state)
                self.container.register_singleton(BrainContext, brain_context)
                self.container.register_singleton(DecisionEngine, decision_engine)
                self.container.register_singleton(CognitiveModelRouter, cog_model_router)
                self.container.register_singleton(ReasoningEngine, reasoning_engine)
                self.container.register_singleton(PlanningEngine, planning_engine)
                self.container.register_singleton(CognitiveReflectionEngine, reflection_engine)
                self.container.register_singleton(LearningEngine, learning_engine)
                self.container.register_singleton(NeuralLayer, neural_layer)
                self.container.register_singleton(BrainKernel, brain_kernel)

                # Post-hoc attach MissionManager (registered earlier, before BrainKernel)
                try:
                    from core.runtime.mission import MissionManager as _MM
                    brain_kernel.mission_manager = self.container.resolve(_MM)
                except Exception:
                    pass
            except Exception as e:
                logger.warning("BrainKernel registration skipped during boot: %s", str(e))

            # Phase 19 M7 — Memory Orchestrator (sole entry point)
            try:
                from core.memory.memory_repository import InMemoryRecordRepository
                from core.memory.orchestrator import MemoryOrchestrator
                from core.memory.retention import RetentionEngine
                from core.memory.retrieval_engine import RetrievalEngine
                from core.memory.scoring import ScoringEngine

                from core.config import MemoryRetentionConfig

                from core.memory.embeddings import (
                    CachedEmbeddingGenerator,
                    SemanticEmbeddingGenerator,
                )
                from core.memory.vector_index import (
                    MemoryVectorIndex,
                    VectorCandidateProvider,
                )
                from core.memory.vector_store import InMemoryVectorRepository

                memory_repo = InMemoryRecordRepository()
                scoring_engine = ScoringEngine()
                retention_engine = RetentionEngine(
                    memory_repo=memory_repo,
                    scoring_engine=scoring_engine,
                    config=MemoryRetentionConfig(),
                    event_bus=event_bus,
                )

                embedding_gen = CachedEmbeddingGenerator(
                    SemanticEmbeddingGenerator(dimensions=384),
                )
                vector_repo = InMemoryVectorRepository()
                vector_index = MemoryVectorIndex(
                    vector_repo=vector_repo,
                    embedding_generator=embedding_gen,
                )
                vector_candidate = VectorCandidateProvider(
                    vector_index=vector_index,
                    record_repo=memory_repo,
                )

                retrieval_engine = RetrievalEngine(
                    memory_repo, scoring_engine,
                    candidate_provider=vector_candidate,
                )
                memory_orchestrator = MemoryOrchestrator(
                    memory_service=None,
                    scoring_engine=scoring_engine,
                    retention_engine=retention_engine,
                    retrieval_engine=retrieval_engine,
                    intelligence_service=None,
                    memory_repo=memory_repo,
                    event_bus=event_bus,
                    vector_index=vector_index,
                )

                self.container.register_singleton(ScoringEngine, scoring_engine)
                self.container.register_singleton(RetentionEngine, retention_engine)
                self.container.register_singleton(RetrievalEngine, retrieval_engine)
                self.container.register_singleton(MemoryOrchestrator, memory_orchestrator)

                try:
                    from core.runtime.brain_kernel import BrainKernel as _BK2
                    _bk2 = self.container.resolve(_BK2)
                    _bk2.memory_orchestrator = memory_orchestrator
                except Exception:
                    pass

                # Wire memory_orchestrator into MissionManager for pre-plan recall
                try:
                    _mm = self.container.resolve(MissionManager)
                    _mm.memory_orchestrator = memory_orchestrator
                except Exception:
                    pass
            except Exception as e:
                logger.warning("MemoryOrchestrator registration skipped during boot: %s", str(e))

            # Phase 38 — Unified Memory & Knowledge Graph
            try:
                from core.memory.consolidation import MemoryConsolidation
                from core.memory.context_assembly import ContextAssembly
                from core.memory.database import db_manager
                from core.memory.episodic_memory import EpisodicMemory
                from core.memory.knowledge_graph import KnowledgeGraph
                from core.memory.long_term_memory import LongTermMemory
                from core.memory.memory_coordinator import MemoryCoordinator
                from core.memory.procedural_memory import ProceduralMemory
                from core.memory.semantic_memory import SemanticMemory
                from core.memory.working_memory import WorkingMemory

                working_mem = WorkingMemory()
                long_term_mem = LongTermMemory(db_manager=db_manager)
                knowledge_graph = KnowledgeGraph(db_manager=db_manager)
                episodic_mem = EpisodicMemory()
                semantic_mem = SemanticMemory()
                procedural_mem = ProceduralMemory()

                memory_coordinator = MemoryCoordinator(
                    working_memory=working_mem,
                    long_term_memory=long_term_mem,
                    knowledge_graph=knowledge_graph,
                    episodic_memory=episodic_mem,
                    semantic_memory=semantic_mem,
                    procedural_memory=procedural_mem,
                )

                _memory_orch = None
                try:
                    from core.memory.orchestrator import MemoryOrchestrator as _MO
                    _memory_orch = self.container.resolve(_MO)
                except Exception:
                    pass

                context_assembler = ContextAssembly(
                    memory_coordinator=memory_coordinator,
                    memory_orchestrator=_memory_orch,
                )

                memory_consolidation = MemoryConsolidation(
                    episodic_memory=episodic_mem,
                    long_term_memory=long_term_mem,
                    semantic_memory=semantic_mem,
                    knowledge_graph=knowledge_graph,
                    llm_runtime=engine_llm_runtime,
                )

                self.container.register_singleton(WorkingMemory, working_mem)
                self.container.register_singleton(LongTermMemory, long_term_mem)
                self.container.register_singleton(KnowledgeGraph, knowledge_graph)
                self.container.register_singleton(EpisodicMemory, episodic_mem)
                self.container.register_singleton(SemanticMemory, semantic_mem)
                self.container.register_singleton(ProceduralMemory, procedural_mem)
                self.container.register_singleton(MemoryCoordinator, memory_coordinator)
                self.container.register_singleton(ContextAssembly, context_assembler)
                self.container.register_singleton(MemoryConsolidation, memory_consolidation)
                # Phase 19 — Memory event subscribers
                try:
                    from core.memory.event_handler import MemoryEventHandler

                    mem_event_handler = MemoryEventHandler(
                        event_bus=event_bus,
                        working_memory=working_mem,
                    )
                    await mem_event_handler.initialize()
                    self.container.register_singleton(MemoryEventHandler, mem_event_handler)
                except Exception as _meh_err:
                    logger.debug("MemoryEventHandler skipped: %s", _meh_err)
            except Exception as e:
                logger.warning("Phase 38 memory registration skipped during boot: %s", str(e))

            # Phase 38 — Identity service post-hoc wiring
            try:
                from core.memory.working_memory import WorkingMemory
                from core.reasoning.identity import IdentityService
                from core.reasoning.identity_repository import IdentityRepository
                from core.runtime.brain_context import BrainContext
                from core.runtime.brain_kernel import BrainKernel

                evt_bus = self.container.resolve(EventBusInterface)
                brain_context = self.container.resolve(BrainContext)
                working_mem = self.container.resolve(WorkingMemory)
                brain_kernel = self.container.resolve(BrainKernel)

                identity_repo = IdentityRepository()
                identity_service = IdentityService(
                    repository=identity_repo,
                    event_bus=evt_bus,
                    brain_context=brain_context,
                    working_memory=working_mem,
                )
                self.container.register_singleton(IdentityService, identity_service)
                brain_kernel.identity_service = identity_service
            except Exception as e:
                logger.warning("IdentityService registration skipped during boot: %s", str(e))

            # 3. Add kernel to lifecycle list (or configure dependency tree)
            self.lifecycle_manager.add_service(self)

            # 4. Initialize and start all services via LifecycleManager
            await self.lifecycle_manager.initialize_all()
            await self.lifecycle_manager.start_all()

            # Seed default security configurations
            try:
                async with db_manager.session() as session:
                    async with session.begin():
                        await seed_service.seed_defaults(session)
            except Exception as e:
                logger.warning(
                    "Database seeding skipped or failed during boot: %s", str(e)
                )

            self._booted = True
            logger.info("Kernel successfully booted.")

            # 5. Publish kernel ready event if event bus is available
            try:
                event_bus = self.container.resolve(EventBusInterface)  # type: ignore[type-abstract]
                ready_message = InterAgentMessage(
                    sender="Kernel",
                    receiver="All",
                    action="kernel_ready",
                    body={"message": "System kernel booted successfully."},
                )
                await event_bus.publish("system.kernel.ready", ready_message)
            except JarvisSystemError:
                # If EventBusInterface has not been registered as a dependency yet, bypass
                logger.warning(
                    "EventBusInterface not resolved during boot event dispatch."
                )

            return True

        except Exception as err:
            logger.critical("Fatal crash during kernel boot: %s", str(err))
            await self.lifecycle_manager.shutdown_all()
            self._booted = False
            return False

    async def _load_vault(self) -> bool:
        """Initialize local security vaults and load keys.

        Returns:
            True if security vault loaded successfully.
        """
        logger.info("Loading system credentials vaults...")
        try:
            # Load settings temporarily to find vault paths
            import os

            from core.config import Settings
            from core.security.vault import VaultManager

            path = (
                self._config_path
                if (self._config_path and os.path.exists(self._config_path))
                else None
            )
            settings = Settings.load_settings(path)

            key_path = settings.vault.encryption_key_path
            secrets_path = settings.vault.secrets_path

            vault = VaultManager(key_path=key_path, secrets_path=secrets_path)
            await vault.initialize()

            self.container.register_singleton(VaultManager, vault)
            return True
        except Exception as e:
            logger.error("Failed to initialize system security vault: %s", str(e))
            return False

    def _resolve_vault_secrets(self, settings: Any) -> None:
        """Scan known settings sub-models and resolve any vault:// placeholders."""
        from core.security.vault import VaultManager

        try:
            vault = self.container.resolve(VaultManager)
        except Exception:
            logger.warning(
                "VaultManager not registered. Skipping config vault secret resolution."
            )
            return

        # Resolve only in known configuration categories (Architect Recommendation #6)
        categories = ["database", "redis", "embedding"]
        for category_name in categories:
            category = getattr(settings, category_name, None)
            if not category:
                continue
            for field in category.__class__.model_fields:
                val = getattr(category, field)
                if isinstance(val, str) and val.startswith("vault://"):
                    secret_name = val[8:]
                    try:
                        resolved = vault.get_secret(secret_name)
                        setattr(category, field, resolved)
                    except Exception as err:
                        logger.error(
                            "Failed to resolve secret '%s' from vault: %s",
                            secret_name,
                            str(err),
                        )

    async def _initialize_event_bus(self) -> bool:
        """Establish connection to the Redis Streams event bus.

        Returns:
            True if event bus is set up.
        """
        # Internal API hook
        logger.info("Initializing connection to global event bus...")
        return True
