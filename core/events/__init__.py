"""JARVIS OS - Event Subsystem.

Exposes event bus interfaces and factory loaders.
"""

from typing import Optional

from core.events.base import EventBus
from core.events.memory_bus import MemoryEventBus
from core.events.redis_bus import RedisEventBus


def create_event_bus(
    environment: str,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_password: Optional[str] = None,
) -> EventBus:
    """Create an EventBus instance based on the system profile environment.

    Args:
        environment: The system execution environment ('development', 'staging', or 'production').
        redis_host: The Redis server host.
        redis_port: The Redis server port.
        redis_password: The Redis connection password.

    Returns:
        MemoryEventBus in development, RedisEventBus in staging or production.
    """
    if environment == "development":
        return MemoryEventBus()
    return RedisEventBus(host=redis_host, port=redis_port, password=redis_password)


__all__ = ["EventBus", "MemoryEventBus", "RedisEventBus", "create_event_bus"]
