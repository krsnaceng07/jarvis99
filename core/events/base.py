"""JARVIS OS - Event Bus Base.

Defines the core EventBus base class extending EventBusInterface.
"""

from abc import ABC

from core.interfaces import EventBusInterface


class EventBus(EventBusInterface, ABC):
    """Abstract Event Bus base class for both Memory and Redis implementations."""
