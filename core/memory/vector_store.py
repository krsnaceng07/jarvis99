"""JARVIS OS - Vector Indexing and Storage.

Implements IVectorStoreRepository with local in-memory/NumPy and Postgres + pgvector backends.
"""

from typing import Any, Dict, List, Optional, cast
from uuid import UUID

import numpy as np
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from core.exceptions import JarvisMemoryError
from core.memory.interfaces import IVectorStoreRepository

# Create a local declarative base for vector records table
Base = declarative_base()


class PostgresVectorRecord(Base):  # type: ignore[misc,valid-type]
    """SQLAlchemy model representing low-level vector records."""

    __tablename__ = "vector_records"

    id = Column(PG_UUID(as_uuid=True), primary_key=True)
    # We load pgvector type inside SQL execution to support dynamic configurations
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)


class InMemoryVectorRepository(IVectorStoreRepository):
    """In-memory vector store utilizing NumPy for cosine distance similarity."""

    def __init__(self) -> None:
        self.vectors: Dict[UUID, List[float]] = {}
        self.metadata: Dict[UUID, Dict[str, Any]] = {}

    async def initialize(self) -> None:
        """No-op for in-memory store."""
        pass

    async def add_vector(
        self, vector_id: UUID, embedding: List[float], metadata: Dict[str, Any]
    ) -> bool:
        self.vectors[vector_id] = embedding
        self.metadata[vector_id] = metadata
        return True

    async def search_vector(
        self,
        embedding: List[float],
        limit: int,
        filter_criteria: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.vectors:
            return []

        results = []
        target_vec = np.array(embedding, dtype=np.float32)
        target_norm = np.linalg.norm(target_vec)

        for vid, vec in self.vectors.items():
            meta = self.metadata.get(vid, {})

            # Filter checking
            if filter_criteria:
                match = True
                for k, v in filter_criteria.items():
                    if meta.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            v_arr = np.array(vec, dtype=np.float32)
            v_norm = np.linalg.norm(v_arr)
            if target_norm == 0 or v_norm == 0:
                score = 0.0
            else:
                score = float(np.dot(target_vec, v_arr) / (target_norm * v_norm))

            results.append({"id": vid, "score": score, "metadata": meta})

        results.sort(key=lambda x: cast(float, x["score"]), reverse=True)
        return results[:limit]

    async def delete_vector(self, vector_id: UUID) -> bool:
        if vector_id in self.vectors:
            del self.vectors[vector_id]
            if vector_id in self.metadata:
                del self.metadata[vector_id]
            return True
        return False


class PostgresVectorRepository(IVectorStoreRepository):
    """Production vector repository utilizing PostgreSQL with pgvector extension."""

    def __init__(self, session: AsyncSession, dimensions: int = 384) -> None:
        """Initialize PostgresVectorRepository.

        Args:
            session: Active database AsyncSession.
            dimensions: Configured vector embedding dimensions.
        """
        self.session = session
        self.dimensions = dimensions

    async def initialize(self) -> None:
        """Ensure pgvector extension is loaded and create the vector_records table."""
        try:
            # Enable pgvector extension
            await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Create table if missing
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS vector_records (
                id UUID PRIMARY KEY,
                embedding vector({self.dimensions}),
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
            )
            """
            await self.session.execute(text(create_table_sql))

            # Create HNSW index for cosine distance if missing
            create_index_sql = """
            CREATE INDEX IF NOT EXISTS idx_vector_records_hnsw
            ON vector_records USING hnsw (embedding vector_cosine_ops)
            """
            await self.session.execute(text(create_index_sql))
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Failed initializing pgvector tables: {str(e)}",
            ) from e

    async def add_vector(
        self, vector_id: UUID, embedding: List[float], metadata: Dict[str, Any]
    ) -> bool:
        if len(embedding) != self.dimensions:
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=(
                    f"Embedding dimension mismatch. Expected {self.dimensions}, "
                    f"got {len(embedding)}"
                ),
            )

        try:
            # Upsert vector record into the database
            import json

            upsert_sql = """
            INSERT INTO vector_records (id, embedding, metadata)
            VALUES (:id, :embedding::vector, :metadata::jsonb)
            ON CONFLICT (id) DO UPDATE
            SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata
            """
            await self.session.execute(
                text(upsert_sql),
                {
                    "id": vector_id,
                    "embedding": str(embedding),
                    "metadata": json.dumps(metadata),
                },
            )
            return True
        except Exception as e:
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Failed adding vector to Postgres: {str(e)}",
            ) from e

    async def search_vector(
        self,
        embedding: List[float],
        limit: int,
        filter_criteria: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            import json

            # Build query logic calculating cosine distance (1 - cosine_similarity)
            # Distance: embedding <=> target_embedding. Similarity is 1 - distance.
            sql = """
            SELECT id, metadata, (1 - (embedding <=> :embedding::vector)) AS score
            FROM vector_records
            """

            params: Dict[str, Any] = {"embedding": str(embedding), "limit": limit}

            if filter_criteria:
                # Add basic metadata matching
                sql += " WHERE metadata @> :filter::jsonb"
                params["filter"] = json.dumps(filter_criteria)

            sql += " ORDER BY embedding <=> :embedding::vector ASC LIMIT :limit"

            res = await self.session.execute(text(sql), params)
            rows = res.all()

            results = []
            for row in rows:
                meta = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                results.append({"id": row[0], "score": float(row[2]), "metadata": meta})
            return results
        except Exception as e:
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Vector search failed: {str(e)}",
            ) from e

    async def delete_vector(self, vector_id: UUID) -> bool:
        try:
            res = await self.session.execute(
                text("DELETE FROM vector_records WHERE id = :id"), {"id": vector_id}
            )
            return bool(getattr(res, "rowcount", 0) > 0)
        except Exception as e:
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Failed deleting vector: {str(e)}",
            ) from e
