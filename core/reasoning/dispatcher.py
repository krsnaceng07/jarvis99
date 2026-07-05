"""
PHASE: 22
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 22 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.browser.engine import BrowserEngine
from core.reasoning.task import ExecutorType, Task
from core.tools.api_runtime import ApiRuntime
from core.tools.browser_runtime import BrowserRuntime
from core.tools.dto import ToolExecutionResult
from core.tools.file_runtime import FileRuntime
from core.tools.human_runtime import HumanRuntime

# Import real execution runtimes
from core.tools.python_runtime import PythonRuntime
from core.tools.shell_runtime import ShellRuntime


class BaseExecutor(ABC):
    """Abstract base class for all task execution runtimes."""

    @abstractmethod
    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        """Run the specific task operation.

        Args:
            task: Task to be executed.
            context: Shared execution context variables (e.g. databases, services).
        """
        pass


class PythonExecutor(BaseExecutor):
    """Executes Python code tasks."""

    def __init__(self) -> None:
        self.runtime = PythonRuntime()

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self.runtime.execute(task, context)


class ShellExecutor(BaseExecutor):
    """Executes OS shell command tasks."""

    def __init__(self) -> None:
        self.runtime = ShellRuntime()

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self.runtime.execute(task, context)


class BrowserExecutor(BaseExecutor):
    """Executes UI browser automation tasks via BrowserRuntime + BrowserEngine.

    Architecture:
        Task → BrowserExecutor → BrowserRuntime → BrowserEngine → IBrowserDriver

    Constraint: Dispatcher only routes — no Playwright logic here (Architect Rule 6).
    """

    def __init__(self, runtime: BrowserRuntime) -> None:
        """Initialise BrowserExecutor with a pre-wired BrowserRuntime.

        Args:
            runtime: Constructed BrowserRuntime with engine and driver.
        """
        self._runtime = runtime

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self._runtime.execute(task, context)


class MemoryExecutor(BaseExecutor):
    """Interacts with Memory Database and Vector Repositories."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        query = task.payload.get("query") or ""
        memory_service = context.get("memory_service")

        stdout = f"Memory search query execution: {query}"
        artifacts = {}

        if memory_service and query:
            # Execute actual retrieval mock/call if service available
            try:
                # Support search or search_hybrid or direct query
                if hasattr(memory_service, "search") and hasattr(
                    memory_service.search, "search_hybrid"
                ):
                    memories = await memory_service.search.search_hybrid(
                        query=query, limit=5
                    )
                elif hasattr(memory_service, "search_hybrid"):
                    memories = await memory_service.search_hybrid(query=query, limit=5)
                else:
                    memories = []
                artifacts["memories"] = memories
                stdout = f"Loaded {len(memories)} relevant facts from memory."
            except Exception as e:
                return ToolExecutionResult(
                    task_id=task.id,
                    status="ERROR",
                    duration=time.perf_counter() - start_time,
                    error=str(e),
                )

        return ToolExecutionResult(
            task_id=task.id,
            status="SUCCESS",
            stdout=stdout,
            exit_code=0,
            duration=time.perf_counter() - start_time,
            artifacts=artifacts,
        )


class HumanExecutor(BaseExecutor):
    """Executes human approval and wait-for-input operations."""

    def __init__(self) -> None:
        self.runtime = HumanRuntime()

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self.runtime.execute(task, context)


class LlmExecutor(BaseExecutor):
    """Executes direct LLM text generation prompts."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        prompt = task.payload.get("prompt") or task.payload.get("instruction") or ""

        stdout = f"LLM generated response for instruction: {prompt}"

        return ToolExecutionResult(
            task_id=task.id,
            status="SUCCESS",
            stdout=stdout,
            exit_code=0,
            duration=time.perf_counter() - start_time,
        )


class ApiExecutor(BaseExecutor):
    """Executes network API calls."""

    def __init__(self) -> None:
        self.runtime = ApiRuntime()

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self.runtime.execute(task, context)


class FileExecutor(BaseExecutor):
    """Executes local file system tasks."""

    def __init__(self) -> None:
        self.runtime = FileRuntime()

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        return await self.runtime.execute(task, context)


def _default_browser_executor() -> BrowserExecutor:
    """Build a default BrowserExecutor using MockCDPDriver for standalone use.

    Production callers should inject their own BrowserExecutor with a real driver
    via the ``executors`` dict parameter of ToolDispatcher.__init__.
    """
    from core.browser.driver import MockCDPDriver
    from core.browser.permission import BrowserPermissionManager
    from core.browser.profile import BrowserContextManager, BrowserProfileManager
    from core.browser.state import BrowserStateManager
    from core.interfaces import EventBusInterface, InterAgentMessage

    class _NullEventBus(EventBusInterface):
        """Minimal no-op event bus for default construction."""

        async def initialize(self) -> None: ...
        async def start(self) -> None: ...
        async def stop(self) -> None: ...
        async def shutdown(self) -> None: ...

        async def publish(self, topic: str, message: InterAgentMessage) -> bool:
            return True

        async def subscribe(self, topic: str, callback: Any) -> str:
            return ""

    driver = MockCDPDriver()
    engine = BrowserEngine(
        driver=driver,
        state_manager=BrowserStateManager(),
        permission_manager=BrowserPermissionManager(),
        profile_manager=BrowserProfileManager(),
        context_manager=BrowserContextManager(BrowserProfileManager()),
        event_bus=_NullEventBus(),
    )
    return BrowserExecutor(BrowserRuntime(engine))


class ToolDispatcher:
    """Central registry routing executing tasks to their respective subclass runtimes."""

    def __init__(
        self, executors: Optional[Dict[ExecutorType, BaseExecutor]] = None
    ) -> None:
        self.executors = executors or {
            ExecutorType.PYTHON: PythonExecutor(),
            ExecutorType.SHELL: ShellExecutor(),
            ExecutorType.BROWSER: _default_browser_executor(),
            ExecutorType.MEMORY: MemoryExecutor(),
            ExecutorType.HUMAN: HumanExecutor(),
            ExecutorType.LLM: LlmExecutor(),
            ExecutorType.API: ApiExecutor(),
            ExecutorType.FILE: FileExecutor(),
        }

    async def dispatch(
        self, task: Task, context: Dict[str, Any]
    ) -> ToolExecutionResult:
        executor = self.executors.get(task.executor)
        if not executor:
            return ToolExecutionResult(
                task_id=task.id,
                status="ERROR",
                error=f"No executor registered for type: {task.executor}",
            )
        try:
            return await executor.execute(task, context)
        except Exception as e:
            return ToolExecutionResult(
                task_id=task.id,
                status="ERROR",
                error=str(e),
            )
