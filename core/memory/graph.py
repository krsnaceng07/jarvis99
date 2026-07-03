"""JARVIS OS - Knowledge Graph Storage.

Implements graph models and the BFS-based traversal repository with cycle avoidance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import JarvisMemoryError
from core.memory.interfaces import (
    IKnowledgeGraphRepository,
    MemoryNodeDTO,
    MemoryRelationDTO,
)
from core.memory.models import Base
from core.memory.validator import validate_graph_node, validate_graph_relation

# =====================================================================
# SQLAlchemy Graph Models
# =====================================================================


class GraphNode(Base):  # type: ignore[misc]
    """Represents a unique entity node inside the Knowledge Graph."""

    __tablename__ = "graph_nodes"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    properties = Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class GraphEdge(Base):  # type: ignore[misc]
    """Represents a directional relationship link between two entity nodes."""

    __tablename__ = "graph_edges"

    id = Column(Uuid(as_uuid=True), primary_key=True)
    source_node_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    properties = Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


# =====================================================================
# DTO Converters
# =====================================================================


def to_node_dto(node: Any) -> MemoryNodeDTO:
    """Convert GraphNode ORM model to MemoryNodeDTO."""
    meta_dict: Dict[str, Any] = (
        node.properties
        if isinstance(node.properties, dict)
        else getattr(node, "properties", {})
    )
    return MemoryNodeDTO(
        id=node.id,
        session_id=node.session_id,
        name=node.name,
        type=node.type,
        properties=meta_dict,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def to_relation_dto(edge: Any) -> MemoryRelationDTO:
    """Convert GraphEdge ORM model to MemoryRelationDTO."""
    meta_dict: Dict[str, Any] = (
        edge.properties
        if isinstance(edge.properties, dict)
        else getattr(edge, "properties", {})
    )
    return MemoryRelationDTO(
        id=edge.id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        relation_type=edge.relation_type,
        weight=edge.weight,
        confidence=edge.confidence,
        properties=meta_dict,
        created_at=edge.created_at,
    )


# =====================================================================
# Repository Implementation
# =====================================================================


class PostgresKnowledgeGraphRepository(IKnowledgeGraphRepository):
    """Database repository implementing graph persistences and BFS traversals."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with active session.

        Args:
            session: Active database AsyncSession.
        """
        self.session = session

    async def get_node(self, node_id: UUID) -> Optional[MemoryNodeDTO]:
        """Fetch node record by ID."""
        stmt = select(GraphNode).where(GraphNode.id == node_id)
        res = await self.session.execute(stmt)
        node = res.scalar_one_or_none()
        if node:
            return to_node_dto(node)
        return None

    async def create_node(self, node: MemoryNodeDTO) -> MemoryNodeDTO:
        """Store a new entity node."""
        validation = validate_graph_node(node)
        if not validation.valid:
            raise JarvisMemoryError(
                "MEMORY_INVALID_NODE",
                f"Invalid graph node: {', '.join(validation.errors)}",
            )

        db_node = GraphNode(
            id=node.id,
            session_id=node.session_id,
            name=node.name,
            type=node.type,
            properties=node.properties,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
        self.session.add(db_node)
        await self.session.flush()
        return to_node_dto(db_node)

    async def update_node(
        self, node_id: UUID, updated_fields: Dict[str, Any]
    ) -> Optional[MemoryNodeDTO]:
        """Update properties of an existing entity node."""
        stmt = select(GraphNode).where(GraphNode.id == node_id)
        res = await self.session.execute(stmt)
        db_node = res.scalar_one_or_none()

        if db_node is None:
            return None

        for field, value in updated_fields.items():
            if field == "properties":
                db_node.properties = value
            elif hasattr(db_node, field):
                setattr(db_node, field, value)

        db_node.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        self.session.add(db_node)
        await self.session.flush()
        return to_node_dto(db_node)

    async def create_relation(self, relation: MemoryRelationDTO) -> MemoryRelationDTO:
        """Store a directional relationship link between two nodes."""
        validation = validate_graph_relation(relation)
        if not validation.valid:
            raise JarvisMemoryError(
                "MEMORY_INVALID_RELATION",
                f"Invalid graph relation: {', '.join(validation.errors)}",
            )

        db_edge = GraphEdge(
            id=relation.id,
            source_node_id=relation.source_node_id,
            target_node_id=relation.target_node_id,
            relation_type=relation.relation_type,
            weight=relation.weight,
            confidence=relation.confidence,
            properties=relation.properties,
            created_at=relation.created_at,
        )
        self.session.add(db_edge)
        await self.session.flush()
        return to_relation_dto(db_edge)

    async def get_relations(self, node_id: UUID) -> List[MemoryRelationDTO]:
        """Get all directional relationship links linked to/from the target node."""
        stmt = select(GraphEdge).where(
            (GraphEdge.source_node_id == node_id)
            | (GraphEdge.target_node_id == node_id)
        )
        res = await self.session.execute(stmt)
        edges = res.scalars().all()
        return [to_relation_dto(e) for e in edges]

    async def traverse(
        self, start_node_id: UUID, max_depth: int = 2
    ) -> List[MemoryNodeDTO]:
        """Traverse outbound neighbors BFS-style with strict cycle avoidance."""
        # Retrieve the starting node to ensure it exists
        start_node_dto = await self.get_node(start_node_id)
        if start_node_dto is None:
            return []

        visited: Set[UUID] = {start_node_id}
        current_layer: Set[UUID] = {start_node_id}
        result_nodes: Dict[UUID, MemoryNodeDTO] = {start_node_id: start_node_dto}

        for _ in range(max_depth):
            if not current_layer:
                break

            # Find all outgoing edges from the current layer
            stmt = select(GraphEdge).where(
                GraphEdge.source_node_id.in_(list(current_layer))
            )
            res = await self.session.execute(stmt)
            edges: List[Any] = list(res.scalars().all())

            # Extract target nodes that haven't been visited yet
            next_layer: Set[UUID] = set()
            for edge in edges:
                target_id = edge.target_node_id
                if target_id not in visited:
                    next_layer.add(target_id)
                    visited.add(target_id)

            if not next_layer:
                break

            # Retrieve nodes for the next layer in a single query batch
            node_stmt = select(GraphNode).where(GraphNode.id.in_(list(next_layer)))
            node_res = await self.session.execute(node_stmt)
            db_nodes: List[Any] = list(node_res.scalars().all())

            for db_node in db_nodes:
                result_nodes[db_node.id] = to_node_dto(db_node)

            current_layer = next_layer

        return list(result_nodes.values())
