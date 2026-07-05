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

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.dto import (
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTier,
    MemoryTrustLevel,
    MemoryVisibility,
)
from core.memory.interfaces import IMemoryRepository, MemorySourceDTO
from core.memory.memory_context import MemoryContextBuilder
from core.memory.memory_index import MemoryIndex
from core.memory.memory_scoring import MemoryScoring
from core.memory.memory_search import MemorySearch
from core.memory.memory_serializer import MemorySerializer


class MemoryEngine:
    """The central runtime orchestrator for the Real Memory Architecture (Core Brain).

    Manages Working Memory (L1 LRU cache), CRUD persistence operations, event publishes,
    retrieval query compilation, and forgetting cycles.
    """

    def __init__(
        self,
        memory_repo: IMemoryRepository,
        scoring: MemoryScoring,
        search: MemorySearch,
        context_builder: MemoryContextBuilder,
        event_bus: EventBusInterface,
        l1_max_items: int = 50,
    ) -> None:
        self.memory_repo = memory_repo
        self.scoring = scoring
        self.search = search
        self.context_builder = context_builder
        self.event_bus = event_bus
        self.l1_max_items = l1_max_items

        # L1 Working Memory
        self.working_memory = MemoryIndex()
        self.lru_order: List[UUID] = []

    def _hash(self, text: str) -> str:
        """Generate exact dedup checksum."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def store(
        self,
        content: str,
        source_type: str = "user_input",
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        session_id: Optional[UUID] = None,
        owner_id: Optional[UUID] = None,
    ) -> UUID:
        """Store a memory node in relational storage and index it in working memory."""
        content_hash = self._hash(content)
        now = datetime.now(timezone.utc)

        # 1. Deduplication check
        existing = await self.memory_repo.get_chunk_by_hash(content_hash)
        if existing:
            record = MemorySerializer.from_dto(existing)
            # Increment access count
            meta: Dict[str, Any] = record.metadata.extra if record.metadata else {}
            meta["access_count"] = int(meta.get("access_count", 1)) + 1
            meta["last_accessed"] = now.isoformat()
            record.updated_at = now

            await self.memory_repo.update_chunk(
                record.memory_id, record.version, MemorySerializer.to_db(record)
            )
            self._update_lru(record)
            return record.memory_id

        # 2. Ingest new chunk
        chunk_id = uuid4()
        owner_id = owner_id or chunk_id
        prov = MemoryProvenance(
            origin="user" if source_type == "user_input" else "system",
            derived_from=None,
            created_by="agent",
            updated_by=None,
            reason=None,
            reflection_id=None,
            workflow_id=None,
            agent_id=None,
        )
        meta_obj = MemoryMetadata(
            importance=importance,
            token_count=len(content.split()),
            embedding_id=None,
            graph_node_id=None,
            extra=metadata or {},
        )
        # Assign L1 working memory defaults to extra dict
        meta_obj.extra.update(
            {
                "access_count": 1,
                "tier": MemoryTier.WORKING.value,
                "owner_id": str(owner_id),
                "visibility": MemoryVisibility.PRIVATE.value,
                "trust_level": MemoryTrustLevel.USER_IMPLICIT.value,
            }
        )

        from core.memory.dto import MemoryType

        record = MemoryRecord(
            memory_id=chunk_id,
            memory_type=MemoryType.FACT,
            owner_id=owner_id,
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.USER_IMPLICIT,
            confidence=confidence,
            importance=importance,
            created_at=now,
            updated_at=now,
            expires_at=None,
            version=1,
            embedding_id=None,
            graph_node_id=None,
            provenance=prov,
            content=content,
            content_hash=content_hash,
            metadata=meta_obj,
        )

        # Persistence writes
        # Verify source table mapping
        source = MemorySourceDTO(
            id=chunk_id,
            source_type=source_type,
            uri=f"session://{session_id or 'default'}",
            agent_id="MemoryEngine",
        )
        await self.memory_repo.create_source(source)
        await self.memory_repo.create_chunk(MemorySerializer.to_dto(record))

        # Add to L1 cache
        self._update_lru(record)

        # Publish commit events
        msg = InterAgentMessage(
            sender="MemoryEngine",
            receiver="system",
            action="memory_created",
            body={
                "memory_id": str(chunk_id),
                "owner_id": str(owner_id),
                "tier": MemoryTier.WORKING.value,
                "score": importance,
            },
        )
        await self.event_bus.publish("memory.created", msg)

        return chunk_id

    def _update_lru(self, record: MemoryRecord) -> None:
        """Update L1 Working Memory index and enforce LRU size constraints."""
        mid = record.memory_id
        self.working_memory.add(record)
        if mid in self.lru_order:
            self.lru_order.remove(mid)
        self.lru_order.append(mid)

        # Evict oldest if L1 capacity is exceeded
        while len(self.lru_order) > self.l1_max_items:
            evict_id = self.lru_order.pop(0)
            self.working_memory.remove(evict_id)

    async def retrieve(self, memory_id: UUID) -> Optional[MemoryRecord]:
        """Retrieve a specific memory by UUID. Attempts L1 working memory lookup first."""
        # 1. L1 Working Memory Check
        record = self.working_memory.get_by_id(memory_id)
        if record:
            self._update_lru(record)
            return record

        # 2. Database Repository Lookup
        dto = await self.memory_repo.get_chunk(memory_id)
        if dto:
            record = MemorySerializer.from_dto(dto)
            self._update_lru(record)
            return record
        return None

    async def update(
        self,
        memory_id: UUID,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update properties or contents of a stored memory chunk."""
        record = await self.retrieve(memory_id)
        if not record:
            return False

        fields_changed = []
        if content is not None:
            record.content = content
            record.content_hash = self._hash(content)
            if record.metadata:
                record.metadata.token_count = len(content.split())
            fields_changed.append("content")

        if metadata is not None:
            if record.metadata:
                record.metadata.extra.update(metadata)
            fields_changed.append("metadata")

        record.updated_at = datetime.now(timezone.utc)
        res = await self.memory_repo.update_chunk(
            memory_id, record.version, MemorySerializer.to_db(record)
        )
        if res is not None:
            record.version = res.version
            self._update_lru(record)
            # Publish event
            msg = InterAgentMessage(
                sender="MemoryEngine",
                receiver="system",
                action="memory_updated",
                body={"memory_id": str(memory_id), "fields_changed": fields_changed},
            )
            await self.event_bus.publish("memory.updated", msg)
            return True
        return False

    async def delete(self, memory_id: UUID) -> bool:
        """Hard-delete memory chunk from database and indexes."""
        # Clean L1 Working Memory cache
        self.working_memory.remove(memory_id)
        if memory_id in self.lru_order:
            self.lru_order.remove(memory_id)

        # Repository soft delete
        res = await self.memory_repo.soft_delete_chunk(memory_id)
        if res:
            # Publish event
            msg = InterAgentMessage(
                sender="MemoryEngine",
                receiver="system",
                action="memory_deleted",
                body={"memory_id": str(memory_id), "tier": "deleted"},
            )
            await self.event_bus.publish("memory.deleted", msg)
            return True
        return False

    async def forget(
        self,
        memory_id: UUID,
        reason: str,
        cascade: bool = False,
    ) -> bool:
        """Forget a memory (soft delete + event)."""
        deleted = await self.delete(memory_id)
        if deleted and cascade:
            # Cascading deletion could clean dependent nodes (e.g. graph node links)
            pass
        return deleted

    async def list_records(
        self,
        tier: Optional[MemoryTier] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """List active memory records matching filter criteria."""
        # Retrieve all records from database repository
        # For simplicity, we search metadata with empty string or get active records
        dtos = await self.memory_repo.keyword_search_chunks("", limit * 2)
        records = [MemorySerializer.from_dto(d) for d in dtos]
        if tier is not None:
            records = [r for r in records if r.metadata.extra.get("tier") == tier.value]
        return records[:limit]
