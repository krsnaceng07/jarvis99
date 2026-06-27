"""JARVIS OS - Service Registry.

Maintains a dictionary map of registered services by type or identifier.
"""

from typing import Any, Dict, Type

from core.exceptions import JarvisSystemError


class ServiceRegistry:
    """Registry container mapping interface types to concrete service instances."""

    def __init__(self) -> None:
        """Initialize an empty service registry mapping."""
        self._services: Dict[Type[Any], Any] = {}

    def register(self, service_type: Type[Any], instance: Any) -> None:
        """Register a service instance under its type interface.

        Args:
            service_type: The type interface class (e.g., LifecycleInterface).
            instance: The concrete object instance implementing the interface.

        Raises:
            JarvisSystemError: If the service type is already registered.
        """
        if service_type in self._services:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Service interface '{service_type.__name__}' is already registered.",
            )
        self._services[service_type] = instance

    def get(self, service_type: Type[Any]) -> Any:
        """Retrieve a registered service instance by its type interface.

        Args:
            service_type: The type interface class.

        Returns:
            The concrete registered service instance.

        Raises:
            JarvisSystemError: If no service is registered for this type interface.
        """
        if service_type not in self._services:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"No service registered for interface '{service_type.__name__}'.",
            )
        return self._services[service_type]

    def has(self, service_type: Type[Any]) -> bool:
        """Check if a service interface is registered.

        Args:
            service_type: The type interface class.

        Returns:
            True if registered, False otherwise.
        """
        return service_type in self._services

    def unregister(self, service_type: Type[Any]) -> None:
        """Unregister a service interface.

        Args:
            service_type: The type interface class.

        Raises:
            JarvisSystemError: If the service type is not registered.
        """
        if service_type not in self._services:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Cannot unregister: service type '{service_type.__name__}' is not registered.",
            )
        del self._services[service_type]
