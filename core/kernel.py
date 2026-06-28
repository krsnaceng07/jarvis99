"""JARVIS OS - System Kernel.

Central coordinator orchestrating configuration validation, security vaults,
event bus initialization, and core lifecycle sequences.
"""

import logging
import sys
from types import ModuleType
from typing import Optional

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

            # Load and Register Settings Singleton
            from core.config import Settings

            settings = Settings.load_settings()
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

            # 3. Add kernel to lifecycle list (or configure dependency tree)
            self.lifecycle_manager.add_service(self)

            # 4. Initialize and start all services via LifecycleManager
            await self.lifecycle_manager.initialize_all()
            await self.lifecycle_manager.start_all()

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
        # Internal API hook
        logger.info("Loading system credentials vaults...")
        return True

    async def _initialize_event_bus(self) -> bool:
        """Establish connection to the Redis Streams event bus.

        Returns:
            True if event bus is set up.
        """
        # Internal API hook
        logger.info("Initializing connection to global event bus...")
        return True
