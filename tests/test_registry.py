"""JARVIS OS - Service Registry and Dependency Container Unit Tests.

Verifies service registration, resolution, duplicate handling, and container injections.
"""

import pytest

from core.container import DependencyContainer
from core.exceptions import JarvisSystemError
from core.interfaces import LifecycleInterface
from core.registry import ServiceRegistry


class DummyService(LifecycleInterface):
    """Mock service implementing LifecycleInterface for testing."""

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def test_service_registry_success() -> None:
    """Verify registry registers and retrieves services correctly."""
    registry = ServiceRegistry()
    service = DummyService()

    assert not registry.has(DummyService)
    registry.register(DummyService, service)
    assert registry.has(DummyService)
    assert registry.get(DummyService) is service


def test_service_registry_duplicate_fail() -> None:
    """Verify registering the same interface twice fails with JarvisSystemError."""
    registry = ServiceRegistry()
    service1 = DummyService()
    service2 = DummyService()

    registry.register(DummyService, service1)
    with pytest.raises(JarvisSystemError) as exc_info:
        registry.register(DummyService, service2)
    assert exc_info.value.code == "SYSTEM_001"
    assert "already registered" in exc_info.value.message


def test_service_registry_missing_fail() -> None:
    """Verify retrieving an unregistered interface fails with JarvisSystemError."""
    registry = ServiceRegistry()
    with pytest.raises(JarvisSystemError) as exc_info:
        registry.get(DummyService)
    assert exc_info.value.code == "SYSTEM_001"
    assert "No service registered" in exc_info.value.message


def test_service_registry_unregister() -> None:
    """Verify services can be unregistered successfully."""
    registry = ServiceRegistry()
    service = DummyService()

    registry.register(DummyService, service)
    registry.unregister(DummyService)
    assert not registry.has(DummyService)


def test_service_registry_unregister_missing_fail() -> None:
    """Verify unregistering a missing service fails."""
    registry = ServiceRegistry()
    with pytest.raises(JarvisSystemError):
        registry.unregister(DummyService)


def test_dependency_container_resolution() -> None:
    """Verify dependency container resolves singletons successfully."""
    container = DependencyContainer()
    service = DummyService()

    container.register_singleton(DummyService, service)
    resolved = container.resolve(DummyService)
    assert resolved is service


def test_dependency_container_resolution_fail() -> None:
    """Verify dependency container raises JarvisSystemError for missing dependencies."""
    container = DependencyContainer()
    with pytest.raises(JarvisSystemError) as exc_info:
        container.resolve(DummyService)
    assert exc_info.value.code == "SYSTEM_001"
    assert "Failed to resolve dependency" in exc_info.value.message
