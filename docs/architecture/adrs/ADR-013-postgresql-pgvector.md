# ADR-013: PostgreSQL + pgvector for Relational and Vector Memory

## Status
* **Status:** Accepted
* **Date:** 2026-07-10 (migrated from legacy 06_ARCHITECTURE_DECISION_RECORDS.md ADR-02)
* **Original Date:** Phase 0 (Foundation)
* **Author:** Architecture Team
* **Migration Note:** Originally filed at `docs/06_ARCHITECTURE_DECISION_RECORDS.md` as "ADR-02: PostgreSQL & pgvector for Relational and Vector Memory". Migrated to canonical Nygard format on 2026-07-10.

---

## Context

JARVIS OS needs persistent storage for:

- **System configuration** (Pydantic Settings persisted; see `docs/30_CONFIGURATION_STANDARD.md`).
- **Memory indices** (Phase 19 — tiered memory with retrieval scoring).
- **Vector embeddings** for semantic recall — Phase 19 spec §retrieval.
- **Knowledge Graph** nodes and edges (Phase 38 spec).
- **Logs and audit trails** (audit-agent, decision-traceability chains).
- **Transaction integrity (ACID)** for contract-modifying operations (Phase 32 admin actions).

We evaluated three storage strategies:

1. **Separate relational + vector databases** (PostgreSQL + Pinecone/Qdrant).
2. **Single unified database** (PostgreSQL with `pgvector` extension).
3. **Document store** (MongoDB) with sidecar vector.

---

## Decision

**Use PostgreSQL 15+ with the `pgvector` extension as the unified primary store for relational + vector data.**

Key decisions:

- **One database, two data shapes** — relational tables for metadata + `vector` columns for embeddings.
- **Schema migrations via Alembic** — frozen per `docs/35_DATABASE_STANDARD.md`.
- **JSONB for flexible properties** — used for tier-scoped record payloads (memory, KG node properties).
- **GIN/B-tree indexes** for traditional queries; HNSW indexes via pgvector for vector search.
- **Async driver `asyncpg`** for non-blocking access from FastAPI handlers and async repos.

---

## Consequences

### Positive

- **Single infrastructure requirement** — no Pinecone/Qdrant sidecar; reduces operational surface.
- **Transactional integrity** — ACID guarantees across relational metadata and vector rows.
- **Deep queries** — JOIN relational metadata (tier, timestamp, source) with vector weights in one query.
- **Mature toolchain** — Alembic, asyncpg, pgvector all production-ready.
- **Cost** — open-source; no per-vector licensing cost.

### Negative

- **pgvector is younger** than Pinecone — fewer advanced features (e.g. sparse vectors, native quantization).
- **Single point of failure** — database outage halts memory, KG, config, and audit. Mitigated by replication + backups (Phase 30 cloud sync).
- **Vector index size** — large memory corpus can balloon; requires periodic VACUUM and partition planning.
- **No native horizontal scaling** (yet) — single primary + replicas; true sharding requires future work.

### Risks

- Migrating to a separate vector DB later is **expensive** — every embedding would need re-indexing.
- pgvector version upgrades occasionally require reindexing HNSW indexes.

---

## Compliance & Invariants

- All schema changes MUST go through Alembic migrations; no manual DDL in production.
- Vector columns MUST be typed `vector(N)` with a fixed dimension (current: 1536 for OpenAI embeddings).
- Repository pattern (AGENTS.md §7.7) is mandatory — no raw SQL in `api/` or `tools/`.
- pgvector HNSW indexes MUST be created concurrently (`CREATE INDEX CONCURRENTLY`).
- All embedding inserts MUST include model_id metadata for later re-indexing if the model changes.

---

## Related

- `docs/35_DATABASE_STANDARD.md` — Alembic + indexing conventions
- `docs/architecture/03_DATABASE_SCHEMAS_FREEZE.md` — frozen schemas
- Phase 19 spec §retrieval — vector scoring engine
- Phase 38 spec — unified memory + knowledge graph
- `docs/29_SECRET_MANAGEMENT.md` — credentials for DB access

---

## References

- Original entry: `docs/06_ARCHITECTURE_DECISION_RECORDS.md` ADR-02 (preserved for audit trail)
- Migration record: `.audit/CLEANUP_REPORT.md` (Phase E — 2026-07-10)
