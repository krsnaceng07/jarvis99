"""JARVIS OS - Event-Driven Memory Indexer.

Subscribes to indexing events and populates vector and graph indices asynchronously.
"""

import asyncio
from typing import Set
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.interfaces import (
    IEmbeddingGenerator,
    IKnowledgeGraphRepository,
    IMemoryRepository,
    IVectorStoreRepository,
    MemoryNodeDTO,
)


class MemoryIndexer:
    """Async background worker subscribing to memory events for indexing."""

    def __init__(
        self,
        memory_repo: IMemoryRepository,
        vector_repo: IVectorStoreRepository,
        graph_repo: IKnowledgeGraphRepository,
        embedding_generator: IEmbeddingGenerator,
        event_bus: EventBusInterface,
        dlq_topic: str = "memory.index.failed",
    ) -> None:
        """Initialize MemoryIndexer.

        Args:
            memory_repo: Persistent database repository.
            vector_repo: High-dimensional vector index repository.
            graph_repo: Knowledge Graph repository.
            embedding_generator: Text embedding generator client.
            event_bus: System event bus.
            dlq_topic: Dead Letter Queue (DLQ) topic.
        """
        self.memory_repo = memory_repo
        self.vector_repo = vector_repo
        self.graph_repo = graph_repo
        self.embedding_generator = embedding_generator
        self.event_bus = event_bus
        self.dlq_topic = dlq_topic
        self.processed_event_ids: Set[UUID] = set()

    async def initialize(self) -> None:
        """Subscribe to memory events on the Event Bus."""
        await self.event_bus.subscribe(
            "memory.chunk.created", self.handle_chunk_created
        )
        await self.event_bus.subscribe(
            "memory.chunk.deleted", self.handle_chunk_deleted
        )

    async def handle_chunk_created(self, msg: InterAgentMessage) -> None:
        """Process incoming chunk creation event, generate vector embedding, and link graph."""
        event_id_str = msg.body.get("event_id")
        chunk_id_str = msg.body.get("chunk_id")

        if not event_id_str or not chunk_id_str:
            return

        event_id = UUID(event_id_str)
        chunk_id = UUID(chunk_id_str)

        # 1. Idempotency Check
        if event_id in self.processed_event_ids:
            return

        # 2. Retry loop for indexing
        max_attempts = 3
        attempt = 0
        success = False
        last_error = ""

        while attempt < max_attempts and not success:
            attempt += 1
            try:
                # Fetch persistent relational chunk
                chunk = await self.memory_repo.get_chunk(chunk_id)
                if not chunk:
                    # Relational row missing (maybe deleted), exit retry loop
                    success = True
                    break

                # Generate high-dimensional vector
                embedding = await self.embedding_generator.generate_embedding(
                    chunk.content
                )

                # Save vector mapping to vector store
                vector_meta = {
                    "source_id": str(chunk.source_id),
                    "version": chunk.version,
                }
                await self.vector_repo.add_vector(chunk_id, embedding, vector_meta)

                # Create concept node in Knowledge Graph
                node_name = chunk.content[:30]
                node = MemoryNodeDTO(
                    id=chunk_id,
                    name=node_name,
                    type="Concept",
                    properties={"source_id": str(chunk.source_id)},
                )
                await self.graph_repo.create_node(node)

                success = True
            except Exception as e:
                last_error = str(e)
                # Small backoff before retrying
                await asyncio.sleep(0.01 * attempt)

        if success:
            self.processed_event_ids.add(event_id)
        else:
            # 3. Publish to Dead Letter Queue (DLQ) if all retries fail
            dlq_msg = InterAgentMessage(
                sender="Indexer",
                receiver="DLQ",
                action="indexing_failed",
                body={
                    "event_id": str(event_id),
                    "chunk_id": str(chunk_id),
                    "attempts": attempt,
                    "error": last_error,
                },
            )
            await self.event_bus.publish(self.dlq_topic, dlq_msg)

    async def handle_chunk_deleted(self, msg: InterAgentMessage) -> None:
        """Handle soft deletion event and remove vectors from indices."""
        chunk_id_str = msg.body.get("chunk_id")
        if not chunk_id_str:
            return

        chunk_id = UUID(chunk_id_str)
        # Delete from vector index
        await self.vector_repo.delete_vector(chunk_id)
