"""JARVIS OS - Personal Memory Models.

Defines the SQLAlchemy model representing persistent user personal memories, preference variables, and device sync tags.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from core.memory.models import Base


class PersonalMemory(Base):  # type: ignore[misc]
    """Represents a version-controlled, tier-prioritized user personal memory fact or preference."""

    __tablename__ = "user_personal_memories"

    # Database Identifiers & Key References
    id = Column(String(36), primary_key=True)
    memory_id = Column(String(36), nullable=False, index=True)
    fact = Column(String, nullable=False)
    tier = Column(Integer, nullable=False, default=4)
    namespace = Column(String(50), nullable=False, default="user")
    lock_level = Column(String(20), nullable=False, default="NORMAL")
    version = Column(Integer, nullable=False, default=1)

    # Boolean State Status Flags
    is_active = Column(Boolean, nullable=False, default=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    pinned = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)

    # Evaluation & Scoring Metrics
    confidence = Column(Float, nullable=False, default=1.0)
    frequency = Column(Integer, nullable=False, default=1)
    importance = Column(Integer, nullable=False, default=50)
    importance_reason = Column(String(50), nullable=True)

    # JSON lists and objects
    aliases = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    extra_metadata = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # Embedding Identification Metadata
    embedding_model = Column(String(100), nullable=True)
    embedding_version = Column(String(20), nullable=True)

    # Synchronization Parameters
    sync_version = Column(Integer, nullable=False, default=0)
    updated_by_device = Column(String(100), nullable=True)
    sync_status = Column(String(20), nullable=False, default="SYNCED")

    # Provenance Logs
    source = Column(String(50), nullable=True)
    conversation_id = Column(String(36), nullable=True)
    message_id = Column(String(36), nullable=True)
    created_by = Column(String(36), nullable=True)

    # Datetime Timestamps
    last_confirmed_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_accessed = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
