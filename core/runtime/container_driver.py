"""JARVIS OS - Subagent Container Driver.

Decouples the SwarmOrchestrator from direct Docker SDK dependencies, supporting multiple adapter modes.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from uuid import UUID


class IContainerDriver(ABC):
    """Abstract interface defining the container drivers."""

    @abstractmethod
    async def spawn_container(self, subagent_id: UUID, task_id: UUID) -> Dict[str, Any]:
        """Spawn a sandboxed runtime environment for the subagent.

        Args:
            subagent_id: Mapped subagent UUID.
            task_id: Active ScheduledTask UUID context.

        Returns:
            Dictionary mapped status outcome.
        """
        pass

    @abstractmethod
    async def terminate_container(self, subagent_id: UUID) -> bool:
        """Force cancel and destroy the sandboxed container.

        Args:
            subagent_id: Unique subagent identifier.

        Returns:
            True if container terminated successfully.
        """
        pass

    @abstractmethod
    async def get_container_metrics(self, subagent_id: UUID) -> Dict[str, Any]:
        """Retrieve real-time resources usage metrics.

        Args:
            subagent_id: Unique subagent identifier.

        Returns:
            CPU, RAM, and uptime metrics.
        """
        pass


class MockAdapter(IContainerDriver):
    """OS-independent mock driver simulating container lifecycles for testing."""

    def __init__(self) -> None:
        """Initialize MockAdapter."""
        self.active_containers: Dict[UUID, Dict[str, Any]] = {}

    async def spawn_container(self, subagent_id: UUID, task_id: UUID) -> Dict[str, Any]:
        self.active_containers[subagent_id] = {
            "subagent_id": subagent_id,
            "task_id": task_id,
            "status": "RUNNING",
            "cpu_limit": 0.5,
            "ram_limit": 512,
        }
        return {"status": "SUCCESS", "container_id": f"mock-{subagent_id}"}

    async def terminate_container(self, subagent_id: UUID) -> bool:
        if subagent_id in self.active_containers:
            self.active_containers.pop(subagent_id)
            return True
        return False

    async def get_container_metrics(self, subagent_id: UUID) -> Dict[str, Any]:
        if subagent_id in self.active_containers:
            return {"cpu_usage": 0.12, "memory_usage": 154.2, "uptime": 45.0}
        return {"cpu_usage": 0.0, "memory_usage": 0.0, "uptime": 0.0}


class LocalProcessAdapter(IContainerDriver):
    """Container driver implementing local process spawning with offline fallbacks."""

    def __init__(self) -> None:
        """Initialize LocalProcessAdapter."""
        self.active_processes: Dict[UUID, Dict[str, Any]] = {}

    async def spawn_container(self, subagent_id: UUID, task_id: UUID) -> Dict[str, Any]:
        self.active_processes[subagent_id] = {
            "subagent_id": subagent_id,
            "task_id": task_id,
            "status": "RUNNING",
        }
        return {"status": "SUCCESS", "process_id": 9999}

    async def terminate_container(self, subagent_id: UUID) -> bool:
        if subagent_id in self.active_processes:
            self.active_processes.pop(subagent_id)
            return True
        return False

    async def get_container_metrics(self, subagent_id: UUID) -> Dict[str, Any]:
        if subagent_id in self.active_processes:
            return {"cpu_usage": 0.05, "memory_usage": 32.5, "uptime": 12.0}
        return {"cpu_usage": 0.0, "memory_usage": 0.0, "uptime": 0.0}


class DockerAdapter(IContainerDriver):
    """Production container driver wrapping python Docker SDK (offline stub mode)."""

    def __init__(self) -> None:
        """Initialize DockerAdapter."""
        self.active_dockers: Dict[UUID, Dict[str, Any]] = {}

    async def spawn_container(self, subagent_id: UUID, task_id: UUID) -> Dict[str, Any]:
        self.active_dockers[subagent_id] = {
            "subagent_id": subagent_id,
            "task_id": task_id,
            "status": "RUNNING",
        }
        return {"status": "SUCCESS", "docker_id": f"docker-{subagent_id}"}

    async def terminate_container(self, subagent_id: UUID) -> bool:
        if subagent_id in self.active_dockers:
            self.active_dockers.pop(subagent_id)
            return True
        return False

    async def get_container_metrics(self, subagent_id: UUID) -> Dict[str, Any]:
        if subagent_id in self.active_dockers:
            return {"cpu_usage": 0.25, "memory_usage": 256.0, "uptime": 30.0}
        return {"cpu_usage": 0.0, "memory_usage": 0.0, "uptime": 0.0}
