"""JARVIS OS - Subsystem Lifecycle Manager.

Orchestrates sequential bootstrap and teardown stages for lifecycle services.
"""

import logging
from enum import Enum
from typing import List

from core.exceptions import JarvisSystemError
from core.interfaces import LifecycleInterface

logger = logging.getLogger("jarvis.core.lifecycle")


class LifecycleState(Enum):
    """Enumerate states of the system lifecycle."""

    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    SHUTDOWN = "SHUTDOWN"


class LifecycleManager:
    """Manages sequential boot and shutdown phases for system services."""

    def __init__(self) -> None:
        """Initialize the LifecycleManager with an empty service list and state."""
        self._services: List[LifecycleInterface] = []
        self._state: LifecycleState = LifecycleState.UNINITIALIZED

    def add_service(self, service: LifecycleInterface) -> None:
        """Add a service to the lifecycle orchestration.

        Args:
            service: The service implementing LifecycleInterface.
        """
        self._services.append(service)

    @property
    def state(self) -> LifecycleState:
        """Get the current system lifecycle state.

        Returns:
            The current LifecycleState.
        """
        return self._state

    async def initialize_all(self) -> None:
        """Initialize all registered services in sequential order.

        Raises:
            JarvisSystemError: If any service fails initialization.
        """
        if self._state != LifecycleState.UNINITIALIZED:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Cannot initialize system from state: {self._state.value}",
            )

        for service in self._services:
            name = service.__class__.__name__
            try:
                await service.initialize()
            except Exception as err:
                logger.error("Service '%s' failed to initialize: %s", name, str(err))
                # Ensure we attempt to clean up any initialized services
                self._state = LifecycleState.INITIALIZED
                await self.shutdown_all()
                raise JarvisSystemError(
                    code="SYSTEM_999",
                    message=f"Service '{name}' failed initialization: {str(err)}",
                ) from err

        self._state = LifecycleState.INITIALIZED

    async def start_all(self) -> None:
        """Start all registered services in sequential order.

        Raises:
            JarvisSystemError: If any service fails to start.
        """
        if self._state != LifecycleState.INITIALIZED:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Cannot start system from state: {self._state.value}",
            )

        for service in self._services:
            name = service.__class__.__name__
            try:
                await service.start()
            except Exception as err:
                logger.error("Service '%s' failed to start: %s", name, str(err))
                # Stop currently started services
                self._state = LifecycleState.RUNNING
                await self.stop_all()
                raise JarvisSystemError(
                    code="SYSTEM_999",
                    message=f"Service '{name}' failed to start: {str(err)}",
                ) from err

        self._state = LifecycleState.RUNNING

    async def stop_all(self) -> None:
        """Stop all registered services in reverse sequential order.

        Raises:
            JarvisSystemError: If any service fails to stop.
        """
        if self._state != LifecycleState.RUNNING:
            return

        # Stop in reverse order of startup
        for service in reversed(self._services):
            name = service.__class__.__name__
            try:
                await service.stop()
            except Exception as err:
                logger.error("Service '%s' failed to stop: %s", name, str(err))
                # Continue stopping other services to avoid leaking resources

        self._state = LifecycleState.STOPPED

    async def shutdown_all(self) -> None:
        """Shutdown all registered services in reverse sequential order.

        Raises:
            JarvisSystemError: If any service fails shutdown.
        """
        # Allow shutdown from INITIALIZED or STOPPED states
        if self._state not in (LifecycleState.INITIALIZED, LifecycleState.STOPPED):
            if self._state == LifecycleState.RUNNING:
                await self.stop_all()
            else:
                return

        for service in reversed(self._services):
            name = service.__class__.__name__
            try:
                await service.shutdown()
            except Exception as err:
                logger.error("Service '%s' failed during shutdown: %s", name, str(err))

        self._state = LifecycleState.SHUTDOWN
        self._services.clear()


stream_logger = logging.getLogger("jarvis")
stream_logger.setLevel(logging.INFO)
