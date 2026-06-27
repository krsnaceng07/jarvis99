"""JARVIS OS - Immutable Audit Logging.

Defines the ToolAuditLog SQLAlchemy model and the write-once ImmutableAuditLogger repository.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.future import select

from core.exceptions import JarvisSkillError, JarvisSystemError
from core.memory.database import db_manager
from core.memory.models import Base


class ToolAuditLog(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a write-once immutable tool invocation audit record."""

    __tablename__ = "tool_audit_logs"

    id = Column(String(36), primary_key=True)
    tool_name = Column(String(100), nullable=False)
    caller_id = Column(String(100), nullable=False)
    arguments = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    result = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    timestamp = Column(DateTime, nullable=False)


class ImmutableAuditLogger:
    """Provides append-only persistence for tool invocation logs, blocking modifications and deletions."""

    def __init__(self) -> None:
        pass

    async def log_invocation(
        self,
        audit_id: UUID,
        tool_name: str,
        caller_id: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Create and write an append-only tool audit log entry.

        Args:
            audit_id: Unique log identifier.
            tool_name: Executed tool name.
            caller_id: Requester agent ID.
            arguments: Injected tool execution parameters.
            result: Outputs and execution metrics.

        Raises:
            JarvisSystemError: If database write fails.
        """
        async with db_manager.session() as session:
            try:
                log_entry = ToolAuditLog(
                    id=str(audit_id),
                    tool_name=tool_name,
                    caller_id=caller_id,
                    arguments=arguments,
                    result=result,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(log_entry)
                await session.commit()
            except Exception as err:
                await session.rollback()
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message=f"Failed to write immutable audit log entry: {str(err)}",
                )

    async def get_log(self, audit_id: UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a specific audit log record by its UUID.

        Args:
            audit_id: Target log ID.

        Returns:
            Dictionary containing log fields if found, None otherwise.
        """
        async with db_manager.session() as session:
            try:
                stmt = select(ToolAuditLog).where(ToolAuditLog.id == str(audit_id))
                result = await session.execute(stmt)
                db_log = result.scalars().first()
                if db_log:
                    return {
                        "id": UUID(str(db_log.id)),
                        "tool_name": db_log.tool_name,
                        "caller_id": db_log.caller_id,
                        "arguments": db_log.arguments,
                        "result": db_log.result,
                        "timestamp": db_log.timestamp,
                    }
                return None
            except Exception as err:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message=f"Failed to query audit log {audit_id}: {str(err)}",
                )

    async def delete_log(self, audit_id: UUID) -> None:
        """Explicitly block delete attempts on immutable logs.

        Args:
            audit_id: Target log ID.

        Raises:
            JarvisSkillError: Always raises to prevent deletion.
        """
        raise JarvisSkillError(
            code="SKILL_009",
            message="Tampering detected. Deletion of audit logs is strictly prohibited.",
        )

    async def update_log(self, audit_id: UUID, fields: Dict[str, Any]) -> None:
        """Explicitly block update attempts on immutable logs.

        Args:
            audit_id: Target log ID.
            fields: Intended updates.

        Raises:
            JarvisSkillError: Always raises to prevent updates.
        """
        raise JarvisSkillError(
            code="SKILL_009",
            message="Tampering detected. Modification of audit logs is strictly prohibited.",
        )
