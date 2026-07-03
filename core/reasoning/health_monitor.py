"""JARVIS OS - Provider Health Monitor.

Orchestrates background monitoring and periodic health validation checks for all model providers.
"""

import asyncio
from typing import List, Optional

from core.reasoning.provider import IModelProvider, ModelHealthStatus


class ProviderHealthMonitor:
    """Daemon class executing background health checks and recovery loops for model providers."""

    def __init__(self, providers: List[IModelProvider]) -> None:
        """Initialize ProviderHealthMonitor with a list of IModelProvider instances."""
        self.providers = providers
        self.is_monitoring = False
        self._monitor_task: Optional[asyncio.Task[None]] = None

    async def check_all_providers(self) -> None:
        """Run health validations across all registered model providers."""
        for provider in self.providers:
            status = await provider.health_check()

            # Attempt active recovery check for offline or cooldown providers
            if status in (ModelHealthStatus.OFFLINE, ModelHealthStatus.COOLDOWN):
                try:
                    # Execute a lightweight mock ping generator request
                    await provider.generate("ping")
                    # If succeeds, reset failure history and return online state
                    provider.record_success()
                except Exception:
                    # Still failing, record failure to extend cooldown or keep offline
                    provider.record_failure()

    async def start_monitoring(self, interval_seconds: float = 30.0) -> None:
        """Start the background validation daemon.

        Args:
            interval_seconds: Run cycle sleep duration.
        """
        if self.is_monitoring:
            return

        self.is_monitoring = True

        async def _run_loop() -> None:
            while self.is_monitoring:
                try:
                    await self.check_all_providers()
                except Exception:
                    pass
                await asyncio.sleep(interval_seconds)

        self._monitor_task = asyncio.create_task(_run_loop())

    async def stop_monitoring(self) -> None:
        """Stop the background validation daemon."""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
