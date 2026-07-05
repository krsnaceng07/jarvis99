"""
PHASE: 30
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import logging
import os
import sqlite3
from typing import Any

from core.exceptions import JarvisSystemError

logger = logging.getLogger(__name__)


class ReplicationManager:
    """Coordinates active-passive replication and failover promotion for SQLite databases."""

    def __init__(
        self,
        settings: Any,
        primary_path: str,
        replica_path: str,
    ) -> None:
        self.settings = settings
        self.primary_path = primary_path
        self.replica_path = replica_path

    def _execute_backup(self) -> None:
        """Run standard sqlite3 connection backup synchronously."""
        if not os.path.exists(self.primary_path):
            # Create a blank database file if primary does not exist yet
            conn = sqlite3.connect(self.primary_path)
            conn.close()

        src = sqlite3.connect(self.primary_path)
        dst = sqlite3.connect(self.replica_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()

    async def replicate(self) -> bool:
        """Trigger native backup from active database to passive replica."""
        if self.settings.database.host != "sqlite":
            logger.info("Skip SQLite replication: Active database is not SQLite.")
            return False

        try:
            await asyncio.to_thread(self._execute_backup)
            logger.info(
                "SQLite database replicated successfully from %s to %s.",
                self.primary_path,
                self.replica_path,
            )
            return True
        except Exception as e:
            logger.error("SQLite replication failed: %s", e)
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Database replication failed: {str(e)}",
            ) from e

    def _check_integrity(self) -> bool:
        """Verify the integrity of the passive replica using SQLite integrity check."""
        if not os.path.exists(self.replica_path):
            return False

        conn = sqlite3.connect(self.replica_path)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            row = cursor.fetchone()
            if row and row[0] == "ok":
                return True
            return False
        except Exception as e:
            logger.error("Replica integrity check exception: %s", e)
            return False
        finally:
            conn.close()

    async def verify_replica_integrity(self) -> bool:
        """Check passive replica database file integrity."""
        return await asyncio.to_thread(self._check_integrity)

    async def promote_replica(self) -> bool:
        """Verify passive replica integrity and promote it to active status atomically."""
        if self.settings.database.host != "sqlite":
            logger.info("Skip SQLite promotion: Active database is not SQLite.")
            return False

        # 1. Verify replica integrity before promotion
        is_healthy = await self.verify_replica_integrity()
        if not is_healthy:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message="Replica promotion denied: Passive replica database is missing or corrupted.",
            )

        # 2. Perform atomic promotion on filesystem
        try:
            # Overwrite the primary database with the healthy replica database file
            await asyncio.to_thread(os.replace, self.replica_path, self.primary_path)
            logger.warning(
                "Replication failover complete: promoted passive database %s to active.",
                self.primary_path,
            )
            return True
        except Exception as e:
            logger.critical("Failed to promote replica database: %s", e)
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failover promotion failed: {str(e)}",
            ) from e
