# 25_KNOWLEDGE_GRAPH.md

## Purpose
This document defines the Knowledge Graph specifications for JARVIS OS. It details the entity schemas, relational attributes, triplestore mappings, and graph search algorithms for structural memory recall.

## Scope
Applies to the PostgreSQL graph tables, NetworkX indexer tasks, and entity resolvers inside the Memory Subsystem.

## Graph Schema & Entity Layout
The knowledge graph is stored in relational PostgreSQL tables using a unified node-edge schema. This avoids complex graph databases while retaining ACID guarantees:

### 1. Nodes Table (`graph_nodes`)
| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique identifier for entity |
| `name` | VARCHAR | Entity name (e.g. "FastAPI", "UserMigration") |
| `type` | VARCHAR | Entity type (e.g. "technology", "module", "file", "agent") |
| `properties` | JSONB | Dynamic metadata attributes |
| `created_at` | TIMESTAMP | Timestamp of insertion |

### 2. Edges Table (`graph_edges`)
| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique edge identifier |
| `source_id` | UUID (FK) | Reference to `graph_nodes.id` |
| `target_id` | UUID (FK) | Reference to `graph_nodes.id` |
| `relation` | VARCHAR | Relationship type (e.g. "DEPENDS_ON", "IMPLEMENTS", "MUTATES") |
| `properties` | JSONB | Edge weight, certainty levels, and constraints |

### Graph Search Heuristic
- **Traversal Policy:** Traversal depth for relational queries is capped at a maximum of **3 degrees of separation** (to prevent slow queries and memory drift).
- **Search Flow:** Search targets use semantic embeddings first to find root nodes, followed by edge walks to retrieve related code assets.

## Responsibilities
- **Memory Agent:** Resolves node conflicts, runs traversal queries, and cleanups dead links.
- **Database Administrator:** Optimizes indexing keys on `source_id` and `target_id`.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 7 and Rule 14).

## Interfaces
- Local API queries: `KnowledgeGraph.query_neighbors(node_id: UUID, relation: str)`.

## Examples
- **Correct Entity Linking:** Adding edge "File `api.py`" -> "DEPENDS_ON" -> "Library `FastAPI`".
- **Incorrect Entity Linking:** Creating recursive cycles without weights or definitions (e.g. Node A depends on Node B, Node B depends on Node C, Node C depends on Node A). (Violates clean DAG rules).

## Failure Cases
- **Loose Nodes:** Nodes created without any edges (orphaned data). *Mitigation:* A weekly background task scans `graph_nodes` and removes nodes that have no active incoming or outgoing edges, keeping the database footprint optimized.

## Security Considerations
- Data isolation rules prevent cross-tenant node indexing. Memory graph nodes must contain a `tenant_id` namespace column to ensure users only traverse their own knowledge structures.

## Future Extension
- Migration to specialized graph engines (e.g. Neo4j) is managed under the Database standards and requires updating ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [12_MEMORY_ARCHITECTURE.md](file:///e:/jarvis/docs/12_MEMORY_ARCHITECTURE.md)
- [30_DATABASE_STANDARD.md](file:///e:/jarvis/docs/30_DATABASE_STANDARD.md)
