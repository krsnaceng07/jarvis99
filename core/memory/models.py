"""JARVIS OS - Memory Relational Models.

SQLAlchemy database models for agent sessions, sources, and chunk persistence.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

from core.memory.interfaces import (
    APIBillingLogDTO,
    MemoryChunkDTO,
    MemorySourceDTO,
)

Base = declarative_base()


class AgentSession(Base):  # type: ignore[misc,valid-type]
    """Represents a unique run session of the system."""

    __tablename__ = "agent_sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    status = Column(String(50), nullable=False)
    config = Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )


class MemorySource(Base):  # type: ignore[misc,valid-type]
    """Represents metadata tracking where a memory originated from."""

    __tablename__ = "memory_sources"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    source_type = Column(String(50), nullable=False)
    uri = Column(String(500), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    agent_id = Column(String(100), nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    version = Column(String(50), default="1.0.0", nullable=False)


class MemoryChunk(Base):  # type: ignore[misc,valid-type]
    """Represents the atomic text segment and metadata parameters."""

    __tablename__ = "memory_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    source_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("memory_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(String, nullable=False)
    content_hash = Column(String(64), unique=True, nullable=False)
    token_count = Column(Integer, nullable=False)
    metadata_ = Column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    is_deleted = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    source = relationship("MemorySource", backref="chunks")


# Helper dictionary mappings for converting ORM entities to DTO schemas safely
def to_source_dto(source: Any) -> MemorySourceDTO:
    """Convert MemorySource ORM model to MemorySourceDTO."""
    return MemorySourceDTO(
        id=source.id,
        source_type=source.source_type,
        uri=source.uri,
        timestamp=source.timestamp,
        agent_id=source.agent_id,
        confidence=source.confidence,
        version=source.version,
    )


def to_chunk_dto(chunk: Any) -> MemoryChunkDTO:
    """Convert MemoryChunk ORM model to MemoryChunkDTO."""
    # Avoid JSON serialization mapping crashes by checking dict types
    meta_dict: Dict[str, Any] = (
        chunk.metadata_
        if isinstance(chunk.metadata_, dict)
        else getattr(chunk, "metadata_", {})
    )

    return MemoryChunkDTO(
        id=chunk.id,
        source_id=chunk.source_id,
        content=chunk.content,
        content_hash=chunk.content_hash,
        token_count=chunk.token_count,
        metadata=meta_dict,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at,
        is_deleted=chunk.is_deleted,
        version=chunk.version,
    )


class APIBillingLog(Base):  # type: ignore[misc,valid-type]
    """Represents persistent records of model API calls and costs."""

    __tablename__ = "api_billing_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    provider_name = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    cost = Column(Numeric(18, 10), nullable=False)


def to_billing_log_dto(log: Any) -> APIBillingLogDTO:
    """Convert APIBillingLog ORM model to APIBillingLogDTO."""
    from decimal import Decimal

    return APIBillingLogDTO(
        id=log.id,
        timestamp=log.timestamp,
        provider_name=log.provider_name,
        model_name=log.model_name,
        prompt_tokens=log.prompt_tokens,
        completion_tokens=log.completion_tokens,
        cost=Decimal(str(log.cost)),
    )
