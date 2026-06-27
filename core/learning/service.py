"""JARVIS OS - Learning Engine Coordinator Service.

Orchestrates scraping, context summarization, entity extraction, pgvector inserts, and 30-day expiration checks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.exceptions import JarvisAgentError
from core.learning.extractor import EntityExtractor
from core.learning.scraper import DocumentScraper
from core.learning.summarizer import ContextSummarizer
from core.memory.interfaces import MemoryNode
from core.memory.service import MemoryService


class LearningService:
    """Orchestrates scraping, summarization, entity indexing, and watchdog expiration cycles."""

    def __init__(
        self,
        memory_service: MemoryService,
        scraper: Optional[DocumentScraper] = None,
        summarizer: Optional[ContextSummarizer] = None,
        extractor: Optional[EntityExtractor] = None,
        validity_days: int = 30,
    ) -> None:
        """Initialize LearningService.

        Args:
            memory_service: Core Memory subsystem orchestrator.
            scraper: DocumentScraper instance.
            summarizer: ContextSummarizer instance.
            extractor: EntityExtractor instance.
            validity_days: Default node validity lifespan in days.
        """
        self.memory_service = memory_service
        self.scraper = scraper or DocumentScraper()
        self.summarizer = summarizer or ContextSummarizer()
        self.extractor = extractor or EntityExtractor()
        self.validity_days = validity_days

    async def ingest_url(self, url: str, chunk_id: Optional[UUID] = None) -> UUID:
        """Scrape target URL, summarize context, extract graph entities, and store to memory.

        Args:
            url: Trusted web documentation link.
            chunk_id: Optional pre-allocated chunk UUID.

        Returns:
            UUID of the ingested memory chunk.
        """
        # 1. Scrape URL content
        raw_text = await self.scraper.scrape_url(url)

        # 2. Summarize context
        summary = await self.summarizer.summarize(raw_text)

        # 3. Store to Memory tier with 30-day validity stamp
        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=self.validity_days)
        ).isoformat()
        node = MemoryNode(
            id=chunk_id or uuid4(),
            content=summary,
            metadata={"source_url": url, "valid_until": valid_until},
        )
        chunk_id = await self.memory_service.store(node, tier="Project")

        # 4. Extract and store graph entities & relationships
        entities = await self.extractor.extract_entities(summary)
        from sqlalchemy import select

        from core.memory.graph import GraphNode

        session = getattr(self.memory_service.graph_repo, "session", None)
        resolved_entities = []
        for entity in entities:
            entity.properties["chunk_id"] = str(chunk_id)

            # De-duplication check: check if node with same name exists
            existing_node = None
            if session:
                stmt = select(GraphNode).where(GraphNode.name == entity.name)
                res = await session.execute(stmt)
                existing_node = res.scalar_one_or_none()

            if existing_node:
                entity.id = existing_node.id
            else:
                await self.memory_service.graph_repo.create_node(entity)
            resolved_entities.append(entity)

        relations = await self.extractor.extract_relations(resolved_entities, summary)
        for relation in relations:
            await self.memory_service.graph_repo.create_relation(relation)

        return chunk_id

    async def check_stale_nodes(self) -> List[Dict[str, Any]]:
        """Identify ingested memory chunks whose validity has expired.

        Returns:
            List of stale chunk descriptors.
        """
        stale_nodes: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        # Retrieve all chunks from relational repository using SQLAlchemy select
        from sqlalchemy import select

        from core.memory.models import MemoryChunk, to_chunk_dto

        stmt = select(MemoryChunk).where(MemoryChunk.is_deleted.is_(False))
        session = getattr(self.memory_service.memory_repo, "session", None)
        if not session:
            return []
        res = await session.execute(stmt)
        chunks = res.scalars().all()
        chunk_dtos = [to_chunk_dto(c) for c in chunks]

        for chunk in chunk_dtos:
            valid_until_str = chunk.metadata.get("valid_until")
            if valid_until_str:
                try:
                    # Parse valid_until timestamp
                    # Handle Z format or +/- offset formats cleanly
                    clean_str = valid_until_str.replace("Z", "+00:00")
                    valid_until = datetime.fromisoformat(clean_str)
                    if valid_until < now:
                        stale_nodes.append(
                            {
                                "chunk_id": chunk.id,
                                "source_url": chunk.metadata.get("source_url"),
                                "valid_until": valid_until_str,
                            }
                        )
                except ValueError:
                    pass

        return stale_nodes

    async def refresh_node(self, chunk_id: UUID) -> None:
        """Trigger update refresh sequence for expired chunk.

        Args:
            chunk_id: Target memory chunk UUID.
        """
        chunk = await self.memory_service.memory_repo.get_chunk(chunk_id)
        if not chunk:
            raise JarvisAgentError(
                code="AGENT_999",
                message=f"Memory chunk {chunk_id} not found.",
            )

        url = chunk.metadata.get("source_url")
        if not url:
            raise JarvisAgentError(
                code="AGENT_999",
                message=f"No source URL found in metadata for chunk {chunk_id}.",
            )

        # Delete previous and re-ingest
        # Note: in real db, update content and refresh validity timestamp
        raw_text = await self.scraper.scrape_url(url)
        summary = await self.summarizer.summarize(raw_text)

        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=self.validity_days)
        ).isoformat()
        meta = dict(chunk.metadata)
        meta["valid_until"] = valid_until

        await self.memory_service.memory_repo.update_chunk(
            chunk_id, chunk.version, {"content": summary, "metadata": meta}
        )
