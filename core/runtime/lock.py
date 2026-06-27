"""JARVIS OS - Swarm Distributed Lock Manager.

Enforces concurrency constraints using MemoryLock and RedisLock adapters to avoid double-processing tasks.
"""

from abc import ABC, abstractmethod
from typing import Dict


class ILockManager(ABC):
    """Abstract interface defining the swarm lock managers."""

    @abstractmethod
    async def acquire(
        self, lock_key: str, owner_id: str, lease_time: float = 30.0
    ) -> bool:
        """Attempt to acquire a unique execution lease.

        Args:
            lock_key: Resource key (e.g. 'agent.task.123').
            owner_id: Identifier of requesting coordinator.
            lease_time: Time limit of lock in seconds.

        Returns:
            True if lease acquired, False otherwise.
        """
        pass

    @abstractmethod
    async def release(self, lock_key: str, owner_id: str) -> bool:
        """Release the active lock lease.

        Args:
            lock_key: Mapped resource key.
            owner_id: Identifier of active coordinator.

        Returns:
            True if released successfully.
        """
        pass


class MemoryLock(ILockManager):
    """Local in-memory coordinator lock manager."""

    def __init__(self) -> None:
        """Initialize MemoryLock."""
        self._locks: Dict[str, str] = {}

    async def acquire(
        self, lock_key: str, owner_id: str, lease_time: float = 30.0
    ) -> bool:
        if lock_key not in self._locks:
            self._locks[lock_key] = owner_id
            return True
        return self._locks[lock_key] == owner_id

    async def release(self, lock_key: str, owner_id: str) -> bool:
        if self._locks.get(lock_key) == owner_id:
            self._locks.pop(lock_key, None)
            return True
        return False


class RedisLock(ILockManager):
    """Distributed Redis lock manager (offline stub adapter mode)."""

    def __init__(self) -> None:
        """Initialize RedisLock."""
        self._locks: Dict[str, str] = {}

    async def acquire(
        self, lock_key: str, owner_id: str, lease_time: float = 30.0
    ) -> bool:
        if lock_key not in self._locks:
            self._locks[lock_key] = owner_id
            return True
        return self._locks[lock_key] == owner_id

    async def release(self, lock_key: str, owner_id: str) -> bool:
        if self._locks.get(lock_key) == owner_id:
            self._locks.pop(lock_key, None)
            return True
        return False
