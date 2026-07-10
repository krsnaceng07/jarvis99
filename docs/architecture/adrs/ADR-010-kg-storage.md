# ADR-010: Knowledge Graph Storage Strategy

**Status:** ACCEPTED (pending CR-1907 resolution for type definitions)
**Date:** 2026-07-03
**Deciders:** JARVIS architect (user), Senior Engineer
**Related:** Phase 19 M6, AGENTS.md Â§6.1, Frozen spec Â§16.5/Â§16.6

---

## Context

Phase 19 M6 introduces the Knowledge Graph (KG) as a relationship engine on top of the existing Memory Engine (M0â€“M5). The KG must support:

- **8 node types** (frozen spec Â§16.5): PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, TASK, GOAL, SKILL
- **7 edge types** (frozen spec Â§16.6): KNOWS, WORKS_ON, DEPENDS_ON, OWNS, RELATED_TO, CAUSED_BY, USES
- Immutable node/edge IDs (UUID v4)
- Optimistic concurrency on versioned updates
- Graph traversal (BFS, neighbors, shortest path, cycle detection)
- Future KG operations: merge_nodes, archive, related_entities
- Scale target: 100K nodes, 1M edges (Phase 20+ target)

If CR-1907 is approved, the types extend to 10 node types (+ PROJECT, DOCUMENT) and 8 edge types (âˆ’ KNOWS, WORKS_ON, CAUSED_BY; + MENTIONS, CREATED, PART_OF, REFERENCES). The storage decision below is independent of type set size.

## Decision

**We use PostgreSQL recursive CTE as the Knowledge Graph storage backend.**

### Implementation

- A new table `kg_nodes` and `kg_edges` (migration `alembic/versions/xxxx_add_kg_tables.py`)
- All graph queries (traversal, neighbors, paths) expressed as recursive CTEs over `kg_edges`
- Soft-delete via `valid_to` timestamp (immutable history, archive pattern)
- Optimistic concurrency via `version` column (integer, increments on update)
- GIN/B-tree indexes on `(source_node_id, type)` and `(target_node_id, type)` for traversal performance

### Why PostgreSQL Recursive CTE

| Criterion | PostgreSQL CTE | Neo4j | NetworkX-in-memory |
|---|---|---|---|
| Infrastructure dep | None (already used) | NEW service | None |
| ACID transactions | âœ… | âš ï¸ Requires config | âŒ |
| Scale to 100K nodes, 1M edges | âœ… Verified | âœ… | âŒ Memory-bound |
| Query language | SQL (CTE) | Cypher | Python API |
| Backup/recovery | pg_dump/restore | Neo4j-specific | Process restart |
| Operational complexity | None added | +1 service | None |
| Phase 0â€“18 already use Postgres | âœ… | âŒ | âœ… |

## Alternatives Considered

### Neo4j (graph-specialized DB)
- **Pros:** Native graph query (Cypher), better traversal performance for deep graphs
- **Cons:** New infrastructure (Rule 14 violation), separate backup strategy, separate ops knowledge, Cypher skill not in team
- **Verdict:** Rejected. Adds infra complexity without proportional value at Phase 19 scale.

### NetworkX (in-memory)
- **Pros:** Pure Python, easy testing, zero infrastructure
- **Cons:** Memory-bound (cannot scale beyond ~50K nodes), no persistence, no ACID
- **Verdict:** Rejected. Good for `KGNode` test fixtures, not production storage.

### Custom Rust/Go graph engine
- **Pros:** Optimal performance
- **Cons:** Massive engineering effort, language skill gap, JARVIS is Python-first
- **Verdict:** Rejected. Premature optimization for Phase 19 scale.

## Consequences

### Positive
- Zero new infrastructure (Postgres already in stack)
- All graph operations transactional with rest of memory subsystem
- Backup/restore via existing `pg_dump` workflow
- Tests use in-memory Postgres or `InMemoryGraphRepository` (NetworkX, isolated to tests)

### Negative
- Deep traversals (depth > 5) may need optimization (CTE depth limits)
- Graph-specific features (path-finding algorithms beyond BFS) require manual SQL

### Mitigation
- Configurable `max_depth` per query (default 3, max 8) to prevent runaway queries
- Query timeout (5s default, configurable via `MemoryConfig`)
- Performance budget in artifact 4 (latency targets)

## Future Migration Path

If Phase 25+ requires deeper graph features (e.g., 10M nodes, complex path-finding), adapter layer (`KGRepository` Protocol) enables swap to Neo4j without changing:
- `KGNode` / `KGEdge` DTOs
- `KGValidator`
- `KGService` / orchestrator callers

The Protocol-based design (already in M0 interfaces) ensures the swap is local to repository implementation.

## CR-1907 Dependency

If CR-1907 is approved, the node/edge enums in `core/memory/dto.py` will be extended from 8+7 to 10+8. The storage schema (this ADR) is **unaffected** â€” same tables, same indexes, same CTEs. Only the application-level enum validation changes.

## References

- Phase 19 spec Â§16.5 (KGNodeType frozen enum)
- Phase 19 spec Â§16.6 (KGEdgeType frozen enum)
- AGENTS.md Â§7.4 (layer dependency direction)
- docs/14_MEMORY_ENGINE_FREEZE.md (memory engine freeze)
- docs/architecture/01_ARCHITECTURE_FREEZE.md (layer architecture)
- CR-1907 (pending) â€” spec amendment for 10+8 types
