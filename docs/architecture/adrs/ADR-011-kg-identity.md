# ADR-011: Knowledge Graph — Identity, Versioning, Inference Boundary

**Status:** PROPOSED (pending CR-1907 for type definitions)
**Date:** 2026-07-03
**Deciders:** JARVIS Memory Team
**Related:** Phase 19 M6, spec Â§16 (Knowledge Graph), ADR-001-memory-storage, AGENTS.md Â§7.4

---

## Context

Phase 19 M6 introduces the Knowledge Graph (KG) as a **relationship engine** on top of memory. The KG must:

- **Store nodes** (entities: Person, Organization, Project, etc.) and **edges** (relations: MENTIONS, USES, OWNS, etc.)
- **Traverse** (BFS, neighbors, shortest path) with cycle avoidance
- **Be immutable** (node IDs never reused, soft-delete only)
- **Be versioned** (optimistic concurrency on updates)
- **Pluggable** (KG knowledge feeds back into retrieval as `CandidateProvider`)
- **Pure** (no AI, no LLM, no embedding â€” graph is structural, not semantic)

The KG must integrate with existing memory (M0â€“M5) without creating layer violations. This ADR documents the **architectural decisions**, not the type set (which is in CR-1907).

## Decision

### 1. Storage: PostgreSQL Recursive CTE

**Decision:** Use the same Postgres cluster as Memory. Tables: `kg_nodes`, `kg_edges`. All queries expressed as recursive CTEs.

**Why:** Zero new infrastructure, transactional with rest of memory, scale to 100K nodes / 1M edges verified. See ADR-001 for full reasoning (KG reuses the storage strategy decision).

### 2. Identity: Immutable UUIDs, Soft-Delete Only

**Decision:** Every node and edge has a **UUID v4** assigned at creation. The UUID is **never reused**, even after soft-delete.

- `valid_to` timestamp marks soft-delete (`NULL` = active, non-NULL = deleted at time T)
- Repository excludes soft-deleted by default (`include_deleted=False`)
- Hard-delete is **never exposed** to user code; only an admin archive job can hard-delete after retention period

**Why UUID v4 (not v7, not sequential)?**
- Globally unique without coordination (KG can be distributed in Phase 20+)
- No information leakage (sequential IDs reveal record count)
- Phase 1-12 already uses UUID v4 â€” consistency

**Why immutable IDs?**
- A deleted node's ID can be referenced in audit logs forever
- KG edges can be safely archived and reloaded
- Reference integrity in M7+ (orchestrator stores node IDs in memory records)

### 3. Versioning: Optimistic Concurrency

**Decision:** Every node and edge has a `version: int` column, starting at 1, incrementing on every update.

- Repository `update_node(node, expected_version)` raises `ConcurrentUpdateError` on mismatch
- Caller (orchestrator) re-reads, merges, and retries (max 3 attempts, exponential backoff)

**Why optimistic (not pessimistic locking)?**
- KG is read-heavy (90%+ reads), pessimistic locks would serialize reads
- Distributed future (Phase 20+) requires conflict-free updates
- Conflict rate is low (different agents update different nodes usually)

### 4. Inference Boundary: KG Has No Inference

**Decision:** KG operations are **pure graph operations**: BFS, neighbors, shortest path, cycle detection. **No inference, no LLM, no embedding, no probabilistic reasoning.**

**Why?**
- Inference belongs in the Brain layer (Phase 20+ Agent Runtime)
- KG is **structural** (what is connected to what), not **semantic** (what does the connection mean)
- Mixing inference into KG would violate AGENTS.md Â§7.4 (no LLM in lower layers)
- Future `InferenceEngine` (M6.5+ in M6 sub-milestones) reads KG but is a separate component

```
Storage â† â†’ Traversal â† â†’ Inference (separate component)
                              â†“
                         Calls LLM/embedding
                         (NOT part of KG)
```

### 5. Layer Position: Domain, Not Infrastructure

The KG is in the **Domain** layer (per `docs/architecture/01_ARCHITECTURE_FREEZE.md`):

```
UI  â†’  API  â†’  Brain  â†’  {Domain (KG, Retrieval, Scoring), Tools}  â†’  Infrastructure
```

`KGRepository` (infrastructure) implements `IKGRepository` (domain interface). Domain logic (graph algorithms, cycle detection) lives in `core/memory/kg_engine.py`, **not** in repository.

## Alternatives Considered

### Storage: Neo4j
- **Pros:** Native graph query (Cypher), better traversal perf
- **Cons:** New infra, separate ops, no ACID with rest of memory
- **Verdict:** Rejected. Same as ADR-001.

### Identity: Sequential IDs
- **Pros:** Compact, sortable
- **Cons:** Reveals count, requires coordination
- **Verdict:** Rejected. UUID v4 is consistent with Phase 1-12.

### Versioning: Pessimistic locking
- **Pros:** No conflicts
- **Cons:** Serializes reads, distributed-incompatible
- **Verdict:** Rejected. Optimistic is the modern choice.

### Inference: LLM in KG
- **Pros:** Smart graph completion
- **Cons:** Violates layer rule, non-deterministic, expensive
- **Verdict:** Rejected. Inference in Brain layer, not Domain.

## Consequences

### Positive
- **Consistent with Phase 1-12:** UUIDs, Pydantic DTOs, ABC interfaces, Postgres
- **Future-proof:** adapter pattern allows Neo4j / NetworkX / custom impls
- **Layer-compliant:** no IO in algorithms, no LLM in graph
- **Auditable:** immutable IDs + version + soft-delete = full history

### Negative
- **CTE performance at scale:** depth > 5 may need optimization
- **Optimistic conflicts in high-write scenarios:** retry logic required
- **No semantic reasoning:** "User works_on Jarvis" requires external inference

### Mitigation
- Configurable `max_depth` (default 3, max 8) prevents runaway queries
- Test coverage for concurrent updates (M6.7)
- Future `InferenceEngine` (M6.5+) provides semantic reasoning on top of KG

## Future Changes

- **Phase 20+:** May add distributed KG (sharded by namespace)
- **Phase 24+:** May add `VectorKG` (hybrid graph + vector) if retrieval needs it
- **Possible:** Neo4j adapter if Postgres CTE hits performance wall at >10M edges

Any change to identity scheme (UUID v4) requires CR (breaks audit log references).

## CR-1907 Dependency

This ADR is **type-agnostic** â€” it documents architectural decisions (storage, identity, versioning, inference boundary) but does **not** specify node/edge types. The type set is in CR-1907 (currently: spec Â§16.5/Â§16.6 with 8+7 types, or 10+8 if CR-1907 is approved).

If CR-1907 is approved, this ADR remains unchanged; only the `KGNodeType` and `KGEdgeType` enums in `core/memory/dto.py` extend.

## References

- Phase 19 spec Â§16 (Knowledge Graph)
- Phase 19 spec Â§16.5 (KGNodeType frozen enum)
- Phase 19 spec Â§16.6 (KGEdgeType frozen enum)
- `core/memory/dto.py` (KGNodeType, KGEdgeType enums)
- ADR-001-memory-storage (storage decision)
- AGENTS.md Â§7.4 (layer dependency direction)
- docs/architecture/01_ARCHITECTURE_FREEZE.md
- docs/contracts/knowledge_graph_contract.md (public API)
- docs/failure/knowledge_graph_failure_matrix.md
- docs/performance/knowledge_graph_performance_budget.md
- docs/observability/knowledge_graph_observability_contract.md
- CR-1907 (pending) â€” spec amendment for type set
