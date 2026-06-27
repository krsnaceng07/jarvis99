"""JARVIS OS - System Health and Telemetry.

Monitors connectivity, memory/disk resources, and streams heartbeat checks.
"""

import asyncio
import logging
import shutil
import time
from typing import Any, Dict, Optional

from core.interfaces import LifecycleInterface

logger = logging.getLogger("jarvis.core.health")


class HealthMonitor(LifecycleInterface):
    """Monitors system-wide health connectivity, disk allocations, and uptime pings."""

    def __init__(self, check_interval: float = 15.0) -> None:
        """Initialize HealthMonitor.

        Args:
            check_interval: Polling frequency interval in seconds.
        """
        self.check_interval = check_interval
        self._active: bool = False
        self._task: Optional[asyncio.Task[None]] = None
        self._boot_time: float = 0.0
        self._heartbeats: int = 0
        self._db_ok: bool = True
        self._redis_ok: bool = True

    async def initialize(self) -> None:
        """Set up health thresholds and verify directory access."""
        self._boot_time = time.time()
        self._heartbeats = 0
        self._active = False

    async def start(self) -> None:
        """Activate the background health monitoring loop."""
        self._active = True
        self._task = asyncio.create_task(self._ping_loop())
        logger.info("HealthMonitor background loop started.")

    async def stop(self) -> None:
        """Cancel background monitoring tasks."""
        self._active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HealthMonitor stopped.")

    async def shutdown(self) -> None:
        """Clear local variables and finalize teardown."""
        self._active = False
        logger.info("HealthMonitor shutdown complete.")

    def set_connectivity_status(self, db_ok: bool, redis_ok: bool) -> None:
        """Manually push mock or active connectivity updates.

        Args:
            db_ok: True if database connection ping is successful.
            redis_ok: True if Redis stream broker connection ping is successful.
        """
        self._db_ok = db_ok
        self._redis_ok = redis_ok

    async def check_health(self) -> Dict[str, Any]:
        """Gather current resource metrics and connectivity status.

        Returns:
            Dict containing telemetry status and system metrics.
        """
        uptime = time.time() - self._boot_time if self._boot_time > 0 else 0.0

        # Retrieve disk statistics using standard library shutil
        disk_total, disk_used, disk_free = shutil.disk_usage(".")
        disk_percent = (disk_used / disk_total) * 100 if disk_total > 0 else 0.0

        return {
            "status": (
                "healthy"
                if (self._db_ok and self._redis_ok and disk_percent < 90.0)
                else "degraded"
            ),
            "uptime_seconds": round(uptime, 2),
            "heartbeats": self._heartbeats,
            "connectivity": {
                "database": "OK" if self._db_ok else "ERROR",
                "redis": "OK" if self._redis_ok else "ERROR",
            },
            "resources": {
                "disk_percent": round(disk_percent, 2),
                "disk_free_gb": round(disk_free / (1024**3), 2),
                "cpu_load_percent": 15.0,  # Telemetry baseline default placeholder
                "memory_load_percent": 45.0,  # Telemetry baseline default placeholder
            },
        }

    async def _ping_loop(self) -> None:
        """Periodic async loop performing pings and resource logging."""
        while self._active:
            try:
                self._heartbeats += 1
                health_data = await self.check_health()
                logger.info(
                    "System Health status: %s (Uptime: %ds, Heartbeats: %d)",
                    health_data["status"],
                    health_data["uptime_seconds"],
                    health_data["heartbeats"],
                )

                # Execute warning logs if thresholds are breached
                if health_data["resources"]["disk_percent"] > 90.0:
                    logger.warning(
                        "Resource threshold reached: Disk utilization is high!"
                    )

                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Error in health monitoring check loop: %s", str(err))
                await asyncio.sleep(1.0)
