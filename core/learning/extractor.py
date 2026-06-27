"""JARVIS OS - Knowledge Graph Entity Extractor.

Resolves plain text documentation into structured concepts (nodes) and relation maps (edges).
"""

from typing import List, Optional
from uuid import UUID, uuid4

from core.memory.interfaces import MemoryNodeDTO, MemoryRelationDTO


class EntityExtractor:
    """Parses plain text documentation to extract concepts and entity relationships."""

    def __init__(self) -> None:
        """Initialize EntityExtractor."""
        # Technical keywords to extract as nodes
        self.known_concepts = {
            "playwright",
            "browser",
            "python",
            "scraping",
            "api",
            "database",
            "redis",
            "postgresql",
            "sandbox",
            "docker",
        }

    async def extract_entities(
        self, text: str, session_id: Optional[UUID] = None
    ) -> List[MemoryNodeDTO]:
        """Extract concept entity nodes from text.

        Args:
            text: Input document text.
            session_id: Optional session identifier.

        Returns:
            List of MemoryNodeDTO schemas.
        """
        text_lower = text.lower()
        nodes: List[MemoryNodeDTO] = []

        for concept in self.known_concepts:
            if concept in text_lower:
                node = MemoryNodeDTO(
                    id=uuid4(),
                    session_id=session_id,
                    name=concept.capitalize(),
                    type="concept",
                    properties={"category": "technology", "auto_extracted": True},
                )
                nodes.append(node)

        return nodes

    async def extract_relations(
        self, nodes: List[MemoryNodeDTO], text: str
    ) -> List[MemoryRelationDTO]:
        """Resolve directional relation edges between extracted concept nodes.

        Args:
            nodes: Extracted MemoryNodeDTOs.
            text: Context document text.

        Returns:
            List of MemoryRelationDTO schemas.
        """
        relations: List[MemoryRelationDTO] = []
        node_map = {n.name.lower(): n.id for n in nodes}

        # Rules-based relationship mapping
        # 1. playwright -> depends_on -> browser
        if "playwright" in node_map and "browser" in node_map:
            relations.append(
                MemoryRelationDTO(
                    id=uuid4(),
                    source_node_id=node_map["playwright"],
                    target_node_id=node_map["browser"],
                    relation_type="depends_on",
                    weight=0.9,
                    confidence=1.0,
                )
            )

        # 2. scraping -> references -> api
        if "scraping" in node_map and "api" in node_map:
            relations.append(
                MemoryRelationDTO(
                    id=uuid4(),
                    source_node_id=node_map["scraping"],
                    target_node_id=node_map["api"],
                    relation_type="references",
                    weight=0.8,
                    confidence=0.9,
                )
            )

        # 3. postgresql -> depends_on -> database
        if "postgresql" in node_map and "database" in node_map:
            relations.append(
                MemoryRelationDTO(
                    id=uuid4(),
                    source_node_id=node_map["postgresql"],
                    target_node_id=node_map["database"],
                    relation_type="depends_on",
                    weight=1.0,
                    confidence=1.0,
                )
            )

        # 4. docker -> part_of -> sandbox
        if "docker" in node_map and "sandbox" in node_map:
            relations.append(
                MemoryRelationDTO(
                    id=uuid4(),
                    source_node_id=node_map["docker"],
                    target_node_id=node_map["sandbox"],
                    relation_type="part_of",
                    weight=0.9,
                    confidence=1.0,
                )
            )

        return relations
