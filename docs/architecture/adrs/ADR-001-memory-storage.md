# ADR-001: Memory Storage Strategy

**Status:** Accepted
**Date:** 2026-07-03
**Deciders:** JARVIS Memory Team
**Related:** Phase 19 M2 (Repository), spec §8 (Memory), AGENTS.md §7.7

---

## Context

Phase 19 M2 needs a memory storage backend. The system stores **Memory Records** (chunks with metadata, scores, tier, version). The M2 implementation serves the entire Memory subsystem (M0–M11). Key requirements:

- **Transactional writes** (ACID for promotion, cascade, archive)
- **Versioned records** (optimistic concurrency for race protection)
- **Indexing** for retrieval (memory_id, tier, score, timestamps)
- **Schema evolution** via Alembic
- **Test isolation** (in-memory repo for unit tests, real Postgres for integration)

Storage choice affects all 9 sub-milestones (M0–M9 of Phase 19). Wrong choice = expensive migration.

## Decision

**We use a Protocol-based repository pattern with two implementations:**

1. **`InMemoryRecordRepository`** — pure-Python dict-based, used in unit tests and for ephemeral agent state. No persistence, no concurrency guarantees beyond Python's GIL.

2. **`PostgresRecordRepository`** (planned M2 extension) — SQLAlchemy 2.0 async, PostgreSQL, used in production. ACID transactions, JSONB for properties, GIN/B-tree indexes.

The public interface is **`IMemoryRecordRepository`** (ABC, frozen in `core/memory/interfaces.py`).

### Why Protocol + ABC

| Concern | ABC (abstract class) | Protocol (PEP 544) |
|---|---|---|
| Runtime check | Yes (`isinstance`) | No (structural) |
| Inheritance required | Yes | No |
| Pydantic compat | Easy | Harder |
| Test mocking | Easy | Easy |
| JARVIS preference (Phase 1-12) | ABC | — |

We use **ABC for repository** (need isinstance checks, Pydantic compat) and **Protocol for cross-module** (e.g., `CandidateProvider` in retrieval).

## Alternatives Considered

### Option A: Pure SQLAlchemy ORM (no Protocol layer)
- **Pros:** Less abstraction, simpler code
- **Cons:** Coupled to ORM, harder to swap to NoSQL/different ORM
- **Verdict:** Rejected. Repository pattern provides future-proofing.

### Option B: Single Postgres implementation
- **Pros:** Simpler, no in-memory layer
- **Cons:** Tests require Postgres, slower CI
- **Verdict:** Rejected. Test isolation is critical for fast CI.

### Option C: Document store (MongoDB)
- **Pros:** JSON-native, flexible schema
- **Cons:** New infrastructure dep, weaker transactions, no JOINs for traversal
- **Verdict:** Rejected. JARVIS already uses Postgres, no infra expansion.

### Option D: Embedded SQLite
- **Pros:** Zero infra, file-based
- **Cons:** No concurrent writers, single-process
- **Verdict:** Rejected for production. Could be future test option.

## Consequences

### Positive
- **Test isolation:** unit tests run without Postgres (fast CI, 5x speedup)
- **Future-proof:** new storage backend (distributed, NoSQL) can be added without changing callers
- **Pydantic compat:** ABC works seamlessly with Pydantic DTOs
- **Phase 0-18 alignment:** repository pattern already used elsewhere in JARVIS

### Negative
- **Dual implementation:** must maintain both `InMemory` and `Postgres`
- **Subtle behavior differences:** in-memory doesn't catch all SQL-specific issues (e.g., deadlock detection)
- **Migration burden:** schema changes must work in both impls

### Mitigation
- Integration tests use real Postgres (`test_memory_repository_integration.py`)
- Schema migration tested via Alembic dry-run in CI
- M2.5 (planned) will add Postgres implementation; current M2 has InMemory only

## Future Changes

- **M2.5 (planned):** Add `PostgresRecordRepository` with full ACID + indexing
- **Phase 20+:** May add `DistributedRecordRepository` (e.g., sharded by session_id)
- **Possible:** SQLite impl for single-process deployments

Any change to `IMemoryRecordRepository` requires CR.

## References

- Phase 19 spec §8 (Memory Engine Architecture)
- `core/memory/interfaces.py` (frozen ABC)
- `core/memory/memory_repository.py` (M2 implementation)
- AGENTS.md §7.7 (Repository = CRUD + transactions + versioning + checksums only)
- docs/35_DATABASE_STANDARD.md (DB conventions)
