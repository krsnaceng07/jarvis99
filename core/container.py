"""JARVIS OS - Dependency Injection Container.

Manages instantiation and injection of system-wide dependencies.
"""

from typing import Any, Optional, Type, TypeVar

from core.exceptions import JarvisSystemError
from core.registry import ServiceRegistry

T = TypeVar("T")


class DependencyContainer:
    """Container for resolving and injecting dependencies via a ServiceRegistry."""

    def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
        """Initialize the dependency container.

        Args:
            registry: Optional custom ServiceRegistry. Defaults to a new instance.
        """
        self._registry = registry or ServiceRegistry()

    def register_singleton(self, service_type: Type[Any], instance: Any) -> None:
        """Register a single instance of a class under a type/interface.

        Args:
            service_type: The abstract interface or concrete class type.
            instance: The concrete object instance.

        Raises:
            JarvisSystemError: If the registration fails.
        """
        try:
            self._registry.register(service_type, instance)
        except JarvisSystemError as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Failed to register singleton: {err.message}",
            ) from err

    def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service dependency.

        Args:
            service_type: The type or interface class of the service to retrieve.

        Returns:
            The resolved concrete service instance.

        Raises:
            JarvisSystemError: If the dependency cannot be resolved.
        """
        try:
            resolved: T = self._registry.get(service_type)
            return resolved
        except JarvisSystemError as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Failed to resolve dependency for type '{service_type.__name__}': {err.message}",
            ) from err

    def get_registry(self) -> ServiceRegistry:
        """Retrieve the underlying service registry.

        Returns:
            The ServiceRegistry instance.
        """
        return self._registry
