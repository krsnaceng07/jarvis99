"""JARVIS OS - Subsystem Lifecycle Unit Tests.

Verifies service registration, state machine transitions, start/stop order, and error handling.
"""

import pytest

from core.exceptions import JarvisSystemError
from core.interfaces import LifecycleInterface
from core.lifecycle import LifecycleManager, LifecycleState


class MockLifecycleService(LifecycleInterface):
    """Mock lifecycle service verifying method execution order and counts."""

    def __init__(self, fail_on: str = "") -> None:
        self.initialized = False
        self.started = False
        self.stopped = False
        self.shutdown_called = False
        self._fail_on = fail_on

    async def initialize(self) -> None:
        if self._fail_on == "initialize":
            raise ValueError("Init failed")
        self.initialized = True

    async def start(self) -> None:
        if self._fail_on == "start":
            raise ValueError("Start failed")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.mark.asyncio
async def test_lifecycle_manager_success() -> None:
    """Verify lifecycle manager successfully orchestrates state phases."""
    manager = LifecycleManager()
    service1 = MockLifecycleService()
    service2 = MockLifecycleService()

    manager.add_service(service1)
    manager.add_service(service2)

    assert manager.state is LifecycleState.UNINITIALIZED

    # Initialize
    await manager.initialize_all()
    assert manager.state is LifecycleState.INITIALIZED  # type: ignore[comparison-overlap]
    assert service1.initialized and service2.initialized

    # Start
    await manager.start_all()
    assert manager.state is LifecycleState.RUNNING
    assert service1.started and service2.started

    # Stop
    await manager.stop_all()
    assert manager.state is LifecycleState.STOPPED
    assert service1.stopped and service2.stopped

    # Shutdown
    await manager.shutdown_all()
    assert manager.state is LifecycleState.SHUTDOWN
    assert service1.shutdown_called and service2.shutdown_called


@pytest.mark.asyncio
async def test_lifecycle_manager_init_failure_triggers_cleanup() -> None:
    """Verify service init failure triggers cleanup/shutdown automatically."""
    manager = LifecycleManager()
    service_good = MockLifecycleService()
    service_fail = MockLifecycleService(fail_on="initialize")

    manager.add_service(service_good)
    manager.add_service(service_fail)

    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.initialize_all()

    assert exc_info.value.code == "SYSTEM_999"
    assert "failed initialization" in exc_info.value.message
    # Check that cleanup shutdown was triggered on the good service
    assert service_good.shutdown_called


@pytest.mark.asyncio
async def test_lifecycle_manager_start_failure_triggers_stop() -> None:
    """Verify service start failure triggers stop cascade."""
    manager = LifecycleManager()
    service_good = MockLifecycleService()
    service_fail = MockLifecycleService(fail_on="start")

    manager.add_service(service_good)
    manager.add_service(service_fail)

    await manager.initialize_all()
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.start_all()

    assert exc_info.value.code == "SYSTEM_999"
    # Check that stop cascade was run on the started service
    assert service_good.stopped


@pytest.mark.asyncio
async def test_lifecycle_manager_invalid_transitions() -> None:
    """Verify lifecycle manager throws errors on invalid state transitions."""
    manager = LifecycleManager()
    service = MockLifecycleService()
    manager.add_service(service)

    # Cannot start from UNINITIALIZED
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.start_all()
    assert exc_info.value.code == "SYSTEM_001"

    # Initialize first
    await manager.initialize_all()

    # Cannot initialize twice
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.initialize_all()
    assert exc_info.value.code == "SYSTEM_001"

    # Start
    await manager.start_all()

    # Cannot start twice
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.start_all()
    assert exc_info.value.code == "SYSTEM_001"


class ExceptionService(LifecycleInterface):
    """Mock service that raises exceptions on stop and shutdown."""

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        raise RuntimeError("Stop fail")

    async def shutdown(self) -> None:
        raise RuntimeError("Shutdown fail")


@pytest.mark.asyncio
async def test_lifecycle_manager_service_exceptions() -> None:
    """Verify lifecycle manager handles and logs exceptions thrown in stop/shutdown without halting."""
    manager = LifecycleManager()
    service_fail = ExceptionService()
    service_good = MockLifecycleService()

    manager.add_service(service_fail)
    manager.add_service(service_good)

    await manager.initialize_all()
    await manager.start_all()

    # Stop should catch exception on service_fail and still stop service_good
    await manager.stop_all()
    assert service_good.stopped

    # Shutdown should catch exception on service_fail and still shutdown service_good
    await manager.shutdown_all()
    assert service_good.shutdown_called
