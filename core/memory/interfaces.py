"""JARVIS OS - Memory Interfaces and DTOs.

Declares type-safe data transfer objects and repository interface contracts.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =====================================================================
# Data Transfer Objects (DTOs)
# =====================================================================


class MemoryNode(BaseModel):
    """Representing the high-level memory object used by agents and planners."""

    id: UUID = Field(default_factory=uuid4)
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    importance: float = 0.5
    confidence: float = 1.0


class RetrievalQuery(BaseModel):
    """Representing parameters for hybrid context searches."""

    query_text: str
    limit: int = 5
    min_score: float = 0.3
    depth: int = 2


class MemorySourceDTO(BaseModel):
    """DTO representing origin metadata of any memory."""

    id: UUID = Field(default_factory=uuid4)
    source_type: str  # 'codebase', 'user_input', 'web_page', 'terminal'
    uri: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str
    confidence: float = 1.0
    version: str = "1.0.0"


class MemoryChunkDTO(BaseModel):
    """DTO representing the atomic unit of semantic/vector text storage."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    content: str
    content_hash: str  # SHA256 of the content text for exact-match deduplication
    token_count: int
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: bool = False
    version: int = 1


class MemoryNodeDTO(BaseModel):
    """DTO representing a entity/concept node in the Knowledge Graph."""

    id: UUID = Field(default_factory=uuid4)
    session_id: Optional[UUID] = None
    name: str
    type: str  # 'concept', 'code_symbol', 'file', 'user_preference'
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryRelationDTO(BaseModel):
    """DTO representing a directional connection edge in the Knowledge Graph."""

    id: UUID = Field(default_factory=uuid4)
    source_node_id: UUID
    target_node_id: UUID
    relation_type: str  # 'depends_on', 'part_of', 'references'
    weight: float = 1.0
    confidence: float = 1.0
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class APIBillingLogDTO(BaseModel):
    """DTO representing a persistent model provider billing log entry."""

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal


# =====================================================================
# Repository Interfaces
# =====================================================================


class IEmbeddingGenerator(ABC):
    """Contract for text embedding generation."""

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate high-dimensional vector for a single text input."""
        pass

    @abstractmethod
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate high-dimensional vectors for a list of text inputs."""
        pass


class IVectorStoreRepository(ABC):
    """Contract for low-level vector indexing and search operations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create indexes or local vector tables if they do not exist."""
        pass

    @abstractmethod
    async def add_vector(
        self, vector_id: UUID, embedding: List[float], metadata: Dict[str, Any]
    ) -> bool:
        """Add a vector index mapping to the persistent store."""
        pass

    @abstractmethod
    async def search_vector(
        self,
        embedding: List[float],
        limit: int,
        filter_criteria: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Find nearest neighbor vector mappings (returns a dict containing vector_id and score)."""
        pass

    @abstractmethod
    async def delete_vector(self, vector_id: UUID) -> bool:
        """Remove a vector mapping from the vector index."""
        pass


class IMemoryRepository(ABC):
    """Contract for Memory Storage operations (Working, Session, LongTerm)."""

    @abstractmethod
    async def get_source(self, source_id: UUID) -> Optional[MemorySourceDTO]:
        """Fetch memory source metadata by ID."""
        pass

    @abstractmethod
    async def create_source(self, source: MemorySourceDTO) -> MemorySourceDTO:
        """Create a new persistent memory source metadata record."""
        pass

    @abstractmethod
    async def get_chunk(self, chunk_id: UUID) -> Optional[MemoryChunkDTO]:
        """Fetch memory chunk by ID."""
        pass

    @abstractmethod
    async def get_chunk_by_hash(self, content_hash: str) -> Optional[MemoryChunkDTO]:
        """Fetch memory chunk by content hash to prevent duplicate writes."""
        pass

    @abstractmethod
    async def create_chunk(self, chunk: MemoryChunkDTO) -> MemoryChunkDTO:
        """Create a new memory chunk record."""
        pass

    @abstractmethod
    async def update_chunk(
        self, chunk_id: UUID, current_version: int, updated_fields: Dict[str, Any]
    ) -> Optional[MemoryChunkDTO]:
        """Update a chunk with version increment. Returns updated DTO or None if conflict."""
        pass

    @abstractmethod
    async def soft_delete_chunk(self, chunk_id: UUID) -> bool:
        """Flag a chunk as soft deleted."""
        pass

    @abstractmethod
    async def keyword_search_chunks(
        self, query: str, limit: int
    ) -> List[MemoryChunkDTO]:
        """Perform exact text search on memory chunks content."""
        pass


class IKnowledgeGraphRepository(ABC):
    """Contract for Knowledge Graph relation and entity query operations."""

    @abstractmethod
    async def get_node(self, node_id: UUID) -> Optional[MemoryNodeDTO]:
        """Retrieve a single entity node by ID."""
        pass

    @abstractmethod
    async def create_node(self, node: MemoryNodeDTO) -> MemoryNodeDTO:
        """Create a new entity node."""
        pass

    @abstractmethod
    async def update_node(
        self, node_id: UUID, updated_fields: Dict[str, Any]
    ) -> Optional[MemoryNodeDTO]:
        """Update properties of an existing entity node."""
        pass

    @abstractmethod
    async def create_relation(self, relation: MemoryRelationDTO) -> MemoryRelationDTO:
        """Create a directional edge between two entity nodes."""
        pass

    @abstractmethod
    async def get_relations(self, node_id: UUID) -> List[MemoryRelationDTO]:
        """Get all edges starting or ending at the target node."""
        pass

    @abstractmethod
    async def traverse(
        self, start_node_id: UUID, max_depth: int = 2
    ) -> List[MemoryNodeDTO]:
        """Traverse graph starting at node_id up to max_depth."""
        pass
