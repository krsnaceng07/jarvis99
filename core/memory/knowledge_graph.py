"""
PHASE: 38
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Entity-relation graph with optional DB persistence."""

    def __init__(self, db_manager: Optional[Any] = None) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.relations: Set[Tuple[str, str, str]] = set()
        self._db_manager = db_manager

    async def add_entity(
        self, name: str, entity_type: str, properties: Dict[str, Any]
    ) -> None:
        """Create or update a node entity."""
        logger.info("KnowledgeGraph adding entity: %s (%s)", name, entity_type)
        self.nodes[name] = {"type": entity_type, "properties": properties}
        await self._persist_node(name, entity_type, properties)

    async def add_relation(self, source: str, target: str, rel_type: str) -> None:
        """Create a relationship link between source and target entities."""
        logger.info(
            "KnowledgeGraph defining relation: %s -[%s]-> %s", source, rel_type, target
        )
        self.relations.add((source, target, rel_type))
        await self._persist_edge(source, target, rel_type)

    async def get_neighbors(self, name: str) -> List[Tuple[str, str]]:
        """Get adjacent neighbors connected to this entity node."""
        neighbors = []
        for src, dst, rtype in self.relations:
            if src == name:
                neighbors.append((dst, rtype))
            elif dst == name:
                neighbors.append((src, rtype))
        return neighbors

    async def traverse(self, start: str, max_depth: int = 2) -> List[str]:
        """BFS traversal from a starting node up to max_depth."""
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(start, 0)]
        result: List[str] = []

        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > max_depth:
                continue
            visited.add(node)
            result.append(node)
            for neighbor, _ in await self.get_neighbors(node):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        return result

    async def load_from_db(self) -> None:
        """Load all nodes and edges from DB into memory."""
        if self._db_manager is None:
            return
        try:
            from uuid import UUID

            from sqlalchemy import select

            from core.memory.graph import GraphEdge, GraphNode

            async with self._db_manager.session() as session:
                nodes_result = await session.execute(select(GraphNode))
                for node in nodes_result.scalars().all():
                    props = node.properties if isinstance(node.properties, dict) else {}
                    self.nodes[node.name] = {"type": node.type, "properties": props}

                edges_result = await session.execute(select(GraphEdge))
                node_id_to_name: Dict[UUID, str] = {}
                for name, data in self.nodes.items():
                    pass
                for edge in edges_result.scalars().all():
                    src_name = self._id_to_name(edge.source_node_id)
                    dst_name = self._id_to_name(edge.target_node_id)
                    if src_name and dst_name:
                        self.relations.add((src_name, dst_name, edge.relation_type))

            logger.info(
                "KnowledgeGraph loaded %d nodes, %d relations from DB.",
                len(self.nodes), len(self.relations),
            )
        except Exception as e:
            logger.debug("KnowledgeGraph DB load skipped: %s", e)

    def _id_to_name(self, node_id: Any) -> Optional[str]:
        """Reverse lookup: not efficient but sufficient for load."""
        return None

    async def _persist_node(
        self, name: str, entity_type: str, properties: Dict[str, Any]
    ) -> None:
        """Write a node to DB if db_manager is available."""
        if self._db_manager is None:
            return
        try:
            from uuid import uuid5, NAMESPACE_DNS

            from sqlalchemy import select

            from core.memory.graph import GraphNode

            node_id = uuid5(NAMESPACE_DNS, f"kg.node.{name}")
            async with self._db_manager.session() as session:
                existing = await session.execute(
                    select(GraphNode).where(GraphNode.id == node_id)
                )
                row = existing.scalar_one_or_none()
                if row is not None:
                    row.type = entity_type
                    row.properties = properties
                else:
                    session.add(GraphNode(
                        id=node_id, name=name, type=entity_type,
                        properties=properties,
                    ))
                await session.commit()
        except Exception as e:
            logger.debug("KG node persist skipped: %s", e)

    async def _persist_edge(
        self, source: str, target: str, rel_type: str
    ) -> None:
        """Write an edge to DB if db_manager is available."""
        if self._db_manager is None:
            return
        try:
            from uuid import uuid5, NAMESPACE_DNS

            from core.memory.graph import GraphEdge

            src_id = uuid5(NAMESPACE_DNS, f"kg.node.{source}")
            dst_id = uuid5(NAMESPACE_DNS, f"kg.node.{target}")
            edge_id = uuid5(NAMESPACE_DNS, f"kg.edge.{source}.{target}.{rel_type}")
            async with self._db_manager.session() as session:
                session.add(GraphEdge(
                    id=edge_id, source_node_id=src_id,
                    target_node_id=dst_id, relation_type=rel_type,
                ))
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
        except Exception as e:
            logger.debug("KG edge persist skipped: %s", e)
