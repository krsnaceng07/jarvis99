"""
PHASE: 20
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 20 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from core.memory.dto import (
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTier,
    MemoryTrustLevel,
)
from core.memory.interfaces import MemoryChunkDTO
from core.memory.models import MemoryChunk


class MemorySerializer:
    """Serialization coordinator for converting memory records between different formats.

    Supports conversions between MemoryRecord (canonical DTO), MemoryChunkDTO (legacy DTO),
    MemoryChunk (SQLAlchemy DB Entity), and raw JSON dicts / API envelopes.
    """

    @staticmethod
    def to_json(record: MemoryRecord) -> str:
        """Convert a MemoryRecord DTO to its JSON string representation."""
        return record.model_dump_json()

    @staticmethod
    def from_json(json_str: str) -> MemoryRecord:
        """Parse a MemoryRecord DTO from its JSON string representation."""
        return MemoryRecord.model_validate_json(json_str)

    @classmethod
    def to_dto(cls, record: MemoryRecord) -> MemoryChunkDTO:
        """Convert canonical MemoryRecord to legacy/interface MemoryChunkDTO."""
        # Merge record properties and nested structures into metadata dict for legacy compatibility
        meta_dict = {
            "importance": record.importance,
            "confidence": record.confidence,
            "tier": record.metadata.extra.get("tier", MemoryTier.LONG_TERM)
            if record.metadata
            else MemoryTier.LONG_TERM,
            "owner_id": str(record.owner_id),
            "visibility": record.visibility.value,
            "trust_level": record.trust_level.value,
            "origin": record.provenance.origin,
            "created_by": record.provenance.created_by,
            "updated_by": record.provenance.updated_by,
            "reason": record.provenance.reason,
            "reflection_id": str(record.provenance.reflection_id)
            if record.provenance.reflection_id
            else None,
            "workflow_id": str(record.provenance.workflow_id)
            if record.provenance.workflow_id
            else None,
            "agent_id": str(record.provenance.agent_id)
            if record.provenance.agent_id
            else None,
        }
        if record.metadata and record.metadata.extra:
            meta_dict.update(record.metadata.extra)

        return MemoryChunkDTO(
            id=record.memory_id,
            source_id=record.provenance.reflection_id
            or record.provenance.workflow_id
            or record.provenance.agent_id
            or record.memory_id,  # fallback
            content=record.content,
            content_hash=record.content_hash,
            token_count=record.metadata.token_count if record.metadata else 0,
            metadata=meta_dict,
            created_at=record.created_at,
            updated_at=record.updated_at,
            is_deleted=False,
            version=record.version,
        )

    @classmethod
    def from_dto(cls, dto: MemoryChunkDTO) -> MemoryRecord:
        """Convert legacy/interface MemoryChunkDTO to canonical MemoryRecord."""
        meta = dto.metadata or {}
        # Reconstruct provenance
        provenance = MemoryProvenance(
            origin=meta.get("origin", "system"),
            derived_from=None,
            created_by=meta.get("created_by", "system"),
            updated_by=meta.get("updated_by"),
            reason=meta.get("reason"),
            reflection_id=UUID(meta["reflection_id"])
            if meta.get("reflection_id")
            else None,
            workflow_id=UUID(meta["workflow_id"]) if meta.get("workflow_id") else None,
            agent_id=UUID(meta["agent_id"]) if meta.get("agent_id") else None,
        )
        # Reconstruct metadata
        metadata = MemoryMetadata(
            importance=float(meta.get("importance", 0.5)),
            token_count=dto.token_count,
            embedding_id=UUID(meta["embedding_id"])
            if meta.get("embedding_id")
            else None,
            graph_node_id=UUID(meta["graph_node_id"])
            if meta.get("graph_node_id")
            else None,
            extra=meta,
        )

        return MemoryRecord(
            memory_id=dto.id,
            memory_type=meta.get("memory_type", "fact"),
            owner_id=UUID(meta["owner_id"]) if meta.get("owner_id") else dto.id,
            visibility=meta.get("visibility", "private"),
            trust_level=meta.get("trust_level", MemoryTrustLevel.USER_IMPLICIT.value),
            confidence=float(meta.get("confidence", 1.0)),
            importance=float(meta.get("importance", 0.5)),
            created_at=dto.created_at or datetime.now(timezone.utc),
            updated_at=dto.updated_at or datetime.now(timezone.utc),
            expires_at=meta.get("expires_at"),
            version=dto.version,
            embedding_id=metadata.embedding_id,
            graph_node_id=metadata.graph_node_id,
            provenance=provenance,
            content=dto.content,
            content_hash=dto.content_hash,
            metadata=metadata,
        )

    @classmethod
    def to_db(cls, record: MemoryRecord) -> Dict[str, Any]:
        """Convert a MemoryRecord DTO into a dictionary suitable for SQLAlchemy insert/update."""
        legacy_dto = cls.to_dto(record)
        return {
            "id": legacy_dto.id,
            "source_id": legacy_dto.source_id,
            "content": legacy_dto.content,
            "content_hash": legacy_dto.content_hash,
            "token_count": legacy_dto.token_count,
            "metadata": legacy_dto.metadata,
            "created_at": legacy_dto.created_at,
            "updated_at": legacy_dto.updated_at,
            "is_deleted": legacy_dto.is_deleted,
            "version": legacy_dto.version,
        }

    @classmethod
    def from_db(cls, db_row: Any) -> MemoryRecord:
        """Convert a database row (or MemoryChunk ORM object) to a MemoryRecord DTO."""
        if isinstance(db_row, MemoryChunk):
            from core.memory.models import to_chunk_dto

            dto = to_chunk_dto(db_row)
        else:
            # Assume dict-like row or raw DB record
            dto = MemoryChunkDTO(
                id=db_row["id"],
                source_id=db_row["source_id"],
                content=db_row["content"],
                content_hash=db_row["content_hash"],
                token_count=db_row["token_count"],
                metadata=db_row["metadata"]
                if isinstance(db_row["metadata"], dict)
                else json.loads(db_row["metadata"]),
                created_at=db_row["created_at"],
                updated_at=db_row["updated_at"],
                is_deleted=db_row["is_deleted"],
                version=db_row["version"],
            )
        return cls.from_dto(dto)
